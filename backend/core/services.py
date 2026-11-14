from decimal import Decimal, ROUND_HALF_UP
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from datetime import date, datetime, time, timedelta, timezone
import base64
import json
import logging
import re
import secrets
import urllib.error
import urllib.request
from io import BytesIO
from hashlib import sha256

from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.db.models import Count, Q, Sum
from django.db.models.functions import TruncDay, TruncMonth
from django.utils import timezone as django_timezone
from django.utils.dateparse import parse_date
from rest_framework.exceptions import ValidationError
from rest_framework.exceptions import APIException
from .models import (DailyNutritionSummary, DoctorAccessRequest, Food, FoodImage, FoodLog,
                     FoodNutrition, FoodPrediction, FoodServing, IdempotencyRecord, Meal,
                     MealItem, MediaDeletionJob, ModelVersion, NutrientTarget, NutritionGoal,
                     NutritionRecord, NutritionSource, Profile, RecognitionResult, User,
                     doctor_access_token as generate_doctor_access_token)
from .recognition_labels import model_search_names

logger = logging.getLogger(__name__)

TWO = Decimal('0.01')
NUTRIENT_KEYS = ('kcal', 'protein_g', 'carbs_g', 'fat_g')
FOOD_100G_FIELDS = {'kcal': 'kcal_100g', 'protein_g': 'protein_100g',
                    'carbs_g': 'carbs_100g', 'fat_g': 'fat_100g'}

# --- Recognition adapters ---
# Kept here so RecognitionsView only depends on this one entry point.
_MAX_CANDIDATES = 5
_DEFAULT_VISION_MODELS = {'openai': 'gpt-4o-mini', 'gemini': 'gemini-2.5-flash'}

_RECOGNITION_PROMPT = (
    'You identify food in a meal photo. Look at the image and return JSON only, '
    'shaped exactly like: {"candidates": [{"name": "food name", '
    '"category": "dish or category name", "confidence": 0.0}]}. '
    'Give up to 5 candidates sorted by confidence (0 to 1). Use short common '
    'food or dish names, no portions, no weights, no nutrition estimates. '
    'If the image shows no food, return {"candidates": []}.'
)


class ProviderError(Exception):
    """Cloud recognition call failed; message is a safe internal code."""


class ProviderNotConfigured(Exception):
    pass


class IdempotencyConflict(APIException):
    status_code = 409
    default_detail = 'This operation ID was used for a different meal.'
    default_code = 'idempotency_conflict'


def _provider_request(url, headers, body):
    request = urllib.request.Request(url, data=body, headers=headers, method='POST')
    try:
        with urllib.request.urlopen(request, timeout=settings.AI_TIMEOUT_SECONDS) as response:
            return json.loads(response.read().decode('utf-8'))
    except urllib.error.HTTPError as exc:
        exc.close()
        logger.warning('Vision provider HTTP %s', exc.code)
        raise ProviderError('PROVIDER_ERROR') from None
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        logger.warning('Vision provider unreachable: %s', exc)
        raise ProviderError('PROVIDER_ERROR') from None
    except json.JSONDecodeError:
        raise ProviderError('PROVIDER_ERROR') from None


def _require_json_object(text):
    try:
        parsed = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        raise ProviderError('PROVIDER_ERROR') from None
    candidates = parsed.get('candidates') if isinstance(parsed, dict) else None
    if not isinstance(candidates, list):
        raise ProviderError('PROVIDER_ERROR')
    return candidates


def normalize_candidates(raw_candidates):
    normalized = []
    for entry in raw_candidates[:_MAX_CANDIDATES]:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get('name', '')).strip()[:120]
        if not name:
            continue
        category = str(entry.get('category', '')).strip()[:60]
        try:
            confidence = min(1.0, max(0.0, float(entry.get('confidence', 0))))
        except (TypeError, ValueError):
            confidence = 0.0
        normalized.append({'name': name, 'category': category, 'confidence': round(confidence, 2)})
    normalized.sort(key=lambda item: item['confidence'], reverse=True)
    return normalized[:_MAX_CANDIDATES]


def provider_image_bytes(image):
    """Small flat JPEG copy for provider calls; stored file stays original."""
    flat = image.convert('RGB')
    if max(flat.width, flat.height) > 1280:
        scale = 1280 / max(flat.width, flat.height)
        flat = flat.resize((max(1, round(flat.width * scale)), max(1, round(flat.height * scale))))
    buffer = BytesIO()
    flat.save(buffer, format='JPEG', quality=85)
    return buffer.getvalue(), 'image/jpeg'


def _openai_candidates(api_key, model, image_bytes, mime):
    data_uri = 'data:%s;base64,%s' % (mime, base64.b64encode(image_bytes).decode('ascii'))
    body = json.dumps({
        'model': model,
        'temperature': 0,
        'response_format': {'type': 'json_object'},
        'messages': [
            {'role': 'system', 'content': _RECOGNITION_PROMPT},
            {'role': 'user', 'content': [
                {'type': 'text', 'text': 'What foods are in this meal photo?'},
                {'type': 'image_url', 'image_url': {'url': data_uri}},
            ]},
        ],
    }).encode('utf-8')
    try:
        payload = _provider_request('https://api.openai.com/v1/chat/completions',
                                    {'Authorization': 'Bearer %s' % api_key,
                                     'Content-Type': 'application/json'}, body)
        content = payload['choices'][0]['message']['content']
    except ProviderError:
        raise
    except (KeyError, IndexError, TypeError):
        logger.warning('OpenAI vision response shape unexpected')
        raise ProviderError('PROVIDER_ERROR') from None
    return normalize_candidates(_require_json_object(content))


def _gemini_candidates(api_key, model, image_bytes, mime):
    body = json.dumps({
        'contents': [{'parts': [
            {'text': _RECOGNITION_PROMPT},
            {'inline_data': {'mime_type': mime, 'data': base64.b64encode(image_bytes).decode('ascii')}},
        ]}],
        'generationConfig': {'temperature': 0, 'responseMimeType': 'application/json'},
    }).encode('utf-8')
    try:
        payload = _provider_request('https://generativelanguage.googleapis.com/v1beta/models/%s:generateContent'
                                    % model,
                                    {'x-goog-api-key': api_key, 'Content-Type': 'application/json'}, body)
        parts = payload['candidates'][0]['content']['parts']
        text = ''.join(str(part.get('text', '')) for part in parts if isinstance(part, dict))
    except ProviderError:
        raise
    except (KeyError, IndexError, TypeError):
        logger.warning('Gemini vision response shape unexpected')
        raise ProviderError('PROVIDER_ERROR') from None
    return normalize_candidates(_require_json_object(text))


def recognize_with_provider(image_bytes, mime):
    """Single switch point for local or cloud recognition.

    Returns {'status', 'candidates', 'model_version', 'error_code'} (plus optional
    'analysis' when the DINOv3 + VLM pipeline runs) and never raises for normal
    inference failures; missing/unapproved config counts as unavailable so callers
    fall back to manual logging.
    """
    provider = getattr(settings, 'AI_PROVIDER', '')
    if provider == 'dinov3_vlm':
        return _attach_candidate_nutrition(recognize_dinov3_vlm(image_bytes))
    if provider == 'dinov3':
        from .dinov3_recognition import recognize_dinov3
        res = recognize_dinov3(image_bytes)
        if res.get('status') == 'completed' and getattr(settings, 'AI_VLM_ENABLED', False):
            try:
                vlm_extra = _run_vlm_on_dinov3_candidates(image_bytes, res.get('candidates', []))
                if vlm_extra:
                    res['analysis'] = vlm_extra
            except Exception:
                logger.warning('Optional VLM enrichment skipped during dinov3 recognition', exc_info=True)
        return _attach_candidate_nutrition(res)
    if provider == 'local':
        from .local_recognition import recognize_locally
        return _attach_candidate_nutrition(recognize_locally(image_bytes))
    if provider not in _DEFAULT_VISION_MODELS:
        return {'status': 'unavailable', 'candidates': [], 'model_version': '', 'error_code': 'MODEL_NOT_CONFIGURED'}
    api_key = (getattr(settings, 'AI_API_KEYS', {}) or {}).get(provider, '')
    model = getattr(settings, 'AI_VISION_MODEL', '') or _DEFAULT_VISION_MODELS[provider]
    if not api_key:
        return {'status': 'unavailable', 'candidates': [], 'model_version': '', 'error_code': 'MODEL_NOT_CONFIGURED'}
    adapter = {'openai': _openai_candidates, 'gemini': _gemini_candidates}[provider]
    try:
        candidates = adapter(api_key, model, image_bytes, mime)
    except ProviderError as exc:
        return {'status': 'failed', 'candidates': [], 'model_version': '%s:%s' % (provider, model),
                'error_code': str(exc)}
    return _attach_candidate_nutrition({
        'status': 'completed',
        'candidates': [dict(candidate, food_id=None) for candidate in candidates],
        'model_version': '%s:%s' % (provider, model),
        'error_code': '',
    })


def _attach_candidate_nutrition(res):
    """Attach explicit VLM analysis to the top candidate without fabricating estimates for unanalyzed labels."""
    if not isinstance(res, dict) or res.get('status') != 'completed':
        return res
    candidates = res.get('candidates') or []
    top_analysis = res.get('analysis')
    if top_analysis and candidates and isinstance(candidates[0], dict) and not candidates[0].get('analysis'):
        candidates[0]['analysis'] = top_analysis
    return res


def _run_vlm_on_dinov3_candidates(image_bytes, candidates):
    """Run VLM analysis on the top DINOv3 candidate and validate with Django serializer."""
    if not candidates:
        return None
    top = candidates[0]
    label = top.get('model_label') or top.get('name', '').lower().replace(' ', '_')
    confidence = float(top.get('confidence', 0.0))
    from ml_models.inference.vlm import analyze_with_vlm
    from .serializers import StructuredNutritionAnalysisSerializer

    checkpoint = getattr(settings, 'AI_VLM_CHECKPOINT', None)
    device = getattr(settings, 'AI_VLM_DEVICE', None)
    raw_analysis = analyze_with_vlm(
        image=image_bytes,
        predicted_label=label,
        confidence=confidence,
        checkpoint=checkpoint,
        device=device,
    )
    serializer = StructuredNutritionAnalysisSerializer(data=raw_analysis)
    serializer.is_valid(raise_exception=True)
    return serializer.validated_data


def recognize_dinov3_vlm(image_bytes):
    """Run the full DINOv3 + Fine-Tuned VLM pipeline and format for Recognitions API."""
    from .recognition_labels import model_display_name
    from .serializers import StructuredNutritionAnalysisSerializer

    try:
        from ml_models.inference.pipeline import analyze_food_image
        checkpoint = getattr(settings, 'AI_VLM_CHECKPOINT', None)
        device = getattr(settings, 'AI_VLM_DEVICE', None)
        top_k = getattr(settings, 'AI_DINOV3_TOP_K', 5)
        pipeline_out = analyze_food_image(
            image_bytes,
            checkpoint=checkpoint,
            device=device,
            top_k=top_k,
            run_vlm=True,
        )
        serializer = StructuredNutritionAnalysisSerializer(data=pipeline_out)
        serializer.is_valid(raise_exception=True)
        validated_analysis = serializer.validated_data
    except (ImportError, ModuleNotFoundError):
        logger.exception('DINOv3+VLM dependencies missing')
        return {'status': 'unavailable', 'candidates': [], 'model_version': '', 'error_code': 'LOCAL_DEPENDENCIES_MISSING'}
    except FileNotFoundError:
        logger.exception('DINOv3+VLM model artifacts missing')
        return {'status': 'unavailable', 'candidates': [], 'model_version': '', 'error_code': 'MODEL_NOT_CONFIGURED'}
    except Exception:
        logger.exception('DINOv3+VLM recognition pipeline failed')
        return {'status': 'failed', 'candidates': [], 'model_version': '', 'error_code': 'LOCAL_MODEL_ERROR'}

    top_preds = pipeline_out.get('classification', {}).get('top_predictions', [])
    candidates = []
    for idx, item in enumerate(top_preds):
        cand_entry = {
            'name': model_display_name(item['label']),
            'model_label': item['label'],
            'category': 'Dish',
            'confidence': round(float(item['confidence']), 3),
            'food_id': None,
        }
        if idx == 0:
            cand_entry['analysis'] = validated_analysis
        candidates.append(cand_entry)

    ckpt_tag = validated_analysis.get('vlm_checkpoint') or 'mealsense-vlm-lora'
    return {
        'status': 'completed',
        'model_version': f'local:dinov3+vlm:{ckpt_tag}',
        'error_code': '',
        'candidates': candidates,
        'analysis': validated_analysis,
    }


def validate_vlm_checkpoint_name(checkpoint_name):
    """Validate an optional VLM checkpoint name against the configured allowlist."""
    if checkpoint_name in (None, ''):
        return getattr(settings, 'AI_VLM_CHECKPOINT', 'mealsense-vlm-lora')
    clean = str(checkpoint_name).strip()
    try:
        from ml_models.inference.config import load_ml_config
        allowed = set(load_ml_config().vlm.checkpoints.keys())
    except Exception:
        allowed = {'mealsense-vlm-lora', 'checkpoint-147', 'mealsense-qwen-vl-lora'}
    if clean not in allowed:
        raise ValidationError({'checkpoint': f"Unknown VLM checkpoint '{clean}'."})
    return clean


def ensure_analyzed_catalog_foods(user, analysis):
    """Ensure user-scoped FCTB 2013 ingredient Food records exist for logging without mutating shared catalog rows."""
    from ml_models.inference.nutrition import NutritionValidationProvider

    provider = NutritionValidationProvider()
    ingredient_foods = {}
    with transaction.atomic():
        fctb_source, _ = NutritionSource.objects.get_or_create(
            name='FCTB 2013 - INFS, University of Dhaka',
            defaults={
                'reference': 'Food Composition Table for Bangladesh (INFS, DU, 2013)',
                'is_trusted': False,
            },
        )
        for ing in analysis.get('ingredients', []):
            ing_key = ing.get('ingredient_key') or ing.get('name', '')
            rec = provider.lookup(ing_key)
            if rec is None:
                continue
            # Effective per-100g cooked edible values accounting for cooking yield factor
            yield_factor = max(0.1, float(rec.cooking_yield_factor))
            kcal_100g = (Decimal(str(rec.calories_kcal_100g)) / Decimal(str(yield_factor))).quantize(TWO, rounding=ROUND_HALF_UP)
            prot_100g = (Decimal(str(rec.protein_g_100g)) / Decimal(str(yield_factor))).quantize(TWO, rounding=ROUND_HALF_UP)
            carb_100g = (Decimal(str(rec.carbohydrates_g_100g)) / Decimal(str(yield_factor))).quantize(TWO, rounding=ROUND_HALF_UP)
            fat_100g = (Decimal(str(rec.fat_g_100g)) / Decimal(str(yield_factor))).quantize(TWO, rounding=ROUND_HALF_UP)

            food_obj, _ = Food.objects.get_or_create(
                created_by=user,
                name=rec.display_name[:120],
                defaults={
                    'category': 'Ingredient (FCTB 2013 derived)',
                    'is_active': True,
                    'is_verified': False,
                    'kcal_100g': kcal_100g,
                    'protein_100g': prot_100g,
                    'carbs_100g': carb_100g,
                    'fat_100g': fat_100g,
                    'source': rec.source_citation[:160],
                    'source_ref': f'FCTB Code {rec.fctb_code} (yield factor {yield_factor})',
                },
            )
            if food_obj.kcal_100g is None:
                food_obj.kcal_100g = kcal_100g
                food_obj.protein_100g = prot_100g
                food_obj.carbs_100g = carb_100g
                food_obj.fat_100g = fat_100g
                food_obj.save(update_fields=['kcal_100g', 'protein_100g', 'carbs_100g', 'fat_100g'])

            if not NutritionRecord.objects.filter(food=food_obj, version=1).exists():
                NutritionRecord.objects.create(
                    food=food_obj,
                    source=fctb_source,
                    version=1,
                    basis_quantity=Decimal('100.00'),
                    basis_unit='g edible',
                    nutrient_values={
                        'kcal': str(kcal_100g),
                        'protein_g': str(prot_100g),
                        'carbs_g': str(carb_100g),
                        'fat_g': str(fat_100g),
                        'raw_kcal_100g': str(rec.calories_kcal_100g),
                        'raw_protein_g_100g': str(rec.protein_g_100g),
                        'raw_carbs_g_100g': str(rec.carbohydrates_g_100g),
                        'raw_fat_g_100g': str(rec.fat_g_100g),
                        'cooking_yield_factor': str(yield_factor),
                    },
                    verification_status='user_supplied',
                    calculation_method=f'FCTB 2013 raw-to-cooked yield factor {yield_factor}',
                )

            ingredient_foods[ing.get('name')] = food_obj

    return ingredient_foods


@transaction.atomic
def create_meal_from_analysis(user, prediction: FoodPrediction, analysis: dict, save_data: dict):
    """Persist a Meal and ingredient-level (or dish-level) MealItems from a validated VLM analysis."""
    eaten_at = save_data.get('eaten_at') or django_timezone.now()
    meal_type = save_data.get('meal_type') or 'lunch'
    notes = save_data.get('notes') or ''
    save_mode = save_data.get('save_mode') or 'ingredients'
    portion_override = save_data.get('portion_weight_g')
    operation_id = save_data.get('operation_id')

    est_total_g = Decimal(str(analysis.get('portion', {}).get('estimated_weight_g') or 100)).quantize(TWO, rounding=ROUND_HALF_UP)
    scale = (Decimal(str(portion_override)) / est_total_g) if (portion_override and est_total_g > 0) else Decimal('1')

    ingredient_foods = ensure_analyzed_catalog_foods(user, analysis)
    top_result = RecognitionResult.objects.filter(session=prediction, rank=1).first()

    items_payload = []
    if save_mode == 'ingredients' and analysis.get('ingredients'):
        for idx, ing in enumerate(analysis['ingredients']):
            food_obj = ingredient_foods.get(ing.get('name'))
            if food_obj is None:
                continue
            w_g = (Decimal(str(ing.get('estimated_weight_g', 0))) * scale).quantize(TWO, rounding=ROUND_HALF_UP)
            if w_g <= 0:
                continue
            item_entry = {
                'food_id': food_obj.id,
                'grams': w_g,
            }
            if idx == 0 and top_result and (top_result.food_id is None or top_result.food_id == food_obj.id):
                # Only attach recognition_result_id when food matches or is unlinked
                if top_result.food_id is None:
                    item_entry['recognition_result_id'] = top_result.id
            items_payload.append(item_entry)

    if not items_payload:
        raise ValidationError({'items': 'No grounded ingredients available to save for this analysis.'})

    meal_data = {
        'eaten_at': eaten_at,
        'meal_type': meal_type,
        'notes': notes,
        'image_id': prediction.image_id,
        'items': items_payload,
    }
    if operation_id:
        meal_data['operation_id'] = operation_id

    return create_meal(user, meal_data)


def matched_catalog_foods(candidates, user):
    """Map candidate names to existing catalogue foods the user may pick."""
    foods = list(Food.objects.filter(
        Q(created_by=user) | Q(created_by__isnull=True), is_active=True,
    ).prefetch_related('aliases'))
    foods.sort(key=lambda food: food.created_by_id != user.id)

    def normalized(value):
        return re.sub(r'[^a-z0-9]+', ' ', str(value).casefold()).strip()

    exact_names = {}
    for food in foods:
        values = (food.name, food.name_bn, *(alias.alias for alias in food.aliases.all()))
        for value in values:
            key = normalized(value)
            if key:
                exact_names.setdefault(key, food)

    result = {}
    for candidate in candidates:
        search_names = model_search_names(candidate.get('model_label', ''), candidate['name'])
        food = next((exact_names.get(normalized(name)) for name in search_names
                     if exact_names.get(normalized(name))), None)
        words = [word for word in normalized(candidate['name']).split() if len(word) > 2]
        phrases = [' '.join(words)] + [' '.join(words[index:index + 2]) for index in range(max(0, len(words) - 1))]
        for phrase in phrases if food is None else ():
            if not phrase:
                continue
            food = next((item for item in foods if any(
                phrase in normalized(value) for value in
                (item.name, item.name_bn, *(alias.alias for alias in item.aliases.all()))
            )), None)
            if food:
                break
        if food:
            result[candidate['name']] = str(food.id)
    return result



def nutrient_snapshot(food: Food, grams: Decimal):
    current = FoodNutrition.objects.filter(food=food).select_related('active_record__source').first()
    if current:
        record = current.active_record
    elif food.created_by_id:
        record = (NutritionRecord.objects.filter(food=food, verification_status='user_supplied')
                  .select_related('source').order_by('-version').first())
    else:
        record = (NutritionRecord.objects.filter(food=food, version=1, verification_status='approved')
                  .select_related('source').first())
    values = record.nutrient_values if record else {
        'kcal': str(food.kcal_100g) if food.kcal_100g is not None else None,
        'protein_g': str(food.protein_100g) if food.protein_100g is not None else None,
        'carbs_g': str(food.carbs_100g) if food.carbs_100g is not None else None,
        'fat_g': str(food.fat_100g) if food.fat_100g is not None else None,
    }
    basis_quantity = record.basis_quantity if record else Decimal('100')
    factor = grams / basis_quantity
    nutrient_names = ('kcal', 'protein_g', 'carbs_g', 'fat_g')
    if any(values.get(name) is None for name in nutrient_names):
        raise ValidationError({'items': 'Food is missing a required nutrient value.'})
    try:
        nutrients = {name: (Decimal(str(values[name])) * factor).quantize(TWO, rounding=ROUND_HALF_UP)
                     for name in nutrient_names}
    except (ArithmeticError, ValueError, TypeError):
        raise ValidationError({'items': 'Food has invalid nutrition data.'}) from None
    return {
        **nutrients, 'nutrition_record': record,
        'nutrition_source_snapshot': record.source.name if record else food.source,
        'nutrition_basis_snapshot': f'per {basis_quantity} {record.basis_unit}' if record else 'per 100 g edible',
        'calculation_version': 'v3-1',
    }


def catalog_per_100g_values(food):
    """Per-100 g nutrient values for a food using the same provenance as
    nutrient_snapshot, but tolerating missing values (None instead of raising).
    Values are normalized to a per-100 g basis when the record basis differs.
    """
    current = FoodNutrition.objects.filter(food=food).select_related('active_record__source').first()
    if current:
        record = current.active_record
    elif food.created_by_id:
        record = (NutritionRecord.objects.filter(food=food, verification_status='user_supplied')
                  .select_related('source').order_by('-version').first())
    else:
        record = (NutritionRecord.objects.filter(food=food, version=1, verification_status='approved')
                  .select_related('source').first())
    if record:
        basis = record.basis_quantity if record.basis_quantity else Decimal('100')
        factor = Decimal('100') / basis
        return {name: (None if record.nutrient_values.get(name) is None
                       else Decimal(str(record.nutrient_values[name])) * factor)
                for name in NUTRIENT_KEYS}
    return {name: (None if getattr(food, field) is None else Decimal(str(getattr(food, field))))
            for name, field in FOOD_100G_FIELDS.items()}


def compute_nutrition_preview(user, items):
    """Server-side per-item and meal-total nutrient preview (ADR-008/ADR-012).

    Mirrors nutrient_snapshot()'s provenance-aware lookup but tolerates missing
    values: unknown nutrients propagate as None, never zero ("unknown is not
    zero"). Each item is either a catalog food reference ({food_id, grams}) or
    inline per-100 g values for a food being composed.
    """
    food_ids = [item['food_id'] for item in items if item.get('food_id')]
    foods = {}
    if food_ids:
        queryset = Food.objects.filter(
            Q(created_by=user) | Q(created_by__isnull=True), is_active=True, id__in=food_ids,
        ).select_related('current_nutrition__active_record__source')
        foods = {food.id: food for food in queryset}
    rows = []
    totals = {name: Decimal('0') for name in NUTRIENT_KEYS}
    unknown = {name: False for name in NUTRIENT_KEYS}
    for item in items:
        grams = Decimal(str(item['grams']))
        food_id = item.get('food_id')
        if food_id:
            food = foods.get(food_id)
            if food is None:
                raise ValidationError({'items': 'Food not found or not available to you.'})
            values = catalog_per_100g_values(food)
            source = food.source
        else:
            values = {name: item.get(FOOD_100G_FIELDS[name]) for name in NUTRIENT_KEYS}
            source = 'Inline per-100 g values'
        row = {'key': str(item.get('key') or ''), 'grams': str(grams.quantize(TWO)),
               'food_id': str(food_id) if food_id else None, 'source': source}
        for name in NUTRIENT_KEYS:
            per_100g = values[name]
            if per_100g is None:
                row[name] = None
                unknown[name] = True
            else:
                amount = (Decimal(str(per_100g)) * grams / Decimal('100')).quantize(TWO, rounding=ROUND_HALF_UP)
                row[name] = str(amount)
                totals[name] += amount
        rows.append(row)
    return {
        'items': rows,
        'totals': {name: (None if unknown[name] else str(totals[name])) for name in NUTRIENT_KEYS},
        'pending': unknown['kcal'],
    }


def compute_goal_suggestions(height_cm, weight_kg, gender, age_years):
    """BMI category plus Mifflin-St Jeor energy/macronutrient suggestions.

    Server-side port of the former client calculator (ADR-008/ADR-012); the
    rounding and clamps are kept identical so previously displayed numbers do
    not drift. These are general estimates, not medical assessments.
    """
    if height_cm is None or weight_kg is None:
        return None
    if not Decimal('50') <= height_cm <= Decimal('260') or not Decimal('20') <= weight_kg <= Decimal('350'):
        return None
    height_m = height_cm / Decimal('100')
    bmi_raw = weight_kg / (height_m * height_m)
    healthy_min = (Decimal('18.5') * height_m * height_m).quantize(Decimal('0.1'), rounding=ROUND_HALF_UP)
    healthy_max = (Decimal('24.9') * height_m * height_m).quantize(Decimal('0.1'), rounding=ROUND_HALF_UP)
    effective_age = age_years if age_years is not None and age_years >= 10 else 25
    gender_offset = {'male': Decimal('5'), 'female': Decimal('-161')}.get(gender or '', Decimal('-78'))
    bmr = Decimal('10') * weight_kg + Decimal('6.25') * height_cm - Decimal('5') * effective_age + gender_offset
    tdee = bmr * Decimal('1.375')
    if bmi_raw < Decimal('18.5'):
        category, tone = 'Underweight', 'peach'
        focus = 'Gentle calorie surplus (+300 kcal) to support healthy weight gain.'
        target_kcal, protein_per_kg, fat_share = tdee + Decimal('300'), Decimal('1.8'), Decimal('0.28')
    elif bmi_raw < Decimal('25'):
        category, tone = 'Healthy weight', 'green'
        focus = 'Balanced maintenance energy for your current BMI.'
        target_kcal, protein_per_kg, fat_share = tdee, Decimal('1.6'), Decimal('0.28')
    elif bmi_raw < Decimal('30'):
        category, tone = 'Overweight', 'peach'
        focus = 'Gentle deficit (-300 kcal) with higher protein for steady progress.'
        target_kcal, protein_per_kg, fat_share = tdee - Decimal('300'), Decimal('1.8'), Decimal('0.27')
    else:
        category, tone = 'Obese', 'peach'
        focus = 'Supportive calorie deficit (-450 kcal) prioritizing protein satiety.'
        target_kcal, protein_per_kg, fat_share = tdee - Decimal('450'), Decimal('1.6'), Decimal('0.26')
    kcal = ((min(Decimal('4000'), max(Decimal('1200'), target_kcal)) / Decimal('10'))
            .quantize(Decimal('1'), rounding=ROUND_HALF_UP) * Decimal('10'))
    protein_g = (min(kcal * Decimal('0.35') / Decimal('4'), max(Decimal('50'), weight_kg * protein_per_kg))
                 .quantize(Decimal('1'), rounding=ROUND_HALF_UP))
    fat_g = (kcal * fat_share / Decimal('9')).quantize(Decimal('1'), rounding=ROUND_HALF_UP)
    remaining = max(Decimal('0'), kcal - protein_g * Decimal('4') - fat_g * Decimal('9'))
    carbs_g = (remaining / Decimal('4')).quantize(Decimal('1'), rounding=ROUND_HALF_UP)
    bmi = (bmi_raw * Decimal('10')).quantize(Decimal('1'), rounding=ROUND_HALF_UP) / Decimal('10')
    return {
        'bmi': str(bmi), 'category': category, 'tone': tone, 'focus': focus,
        'healthy_min_kg': str(healthy_min), 'healthy_max_kg': str(healthy_max),
        'kcal': int(kcal), 'protein_g': int(protein_g), 'carbs_g': int(carbs_g), 'fat_g': int(fat_g),
    }


def per_100g_from_analysis(analysis):
    """Derive per-100 g values from an already-validated VLM analysis.

    Keeps the portion-weight division server-side (ADR-008) so the client no
    longer derives catalog values from per-portion numbers. Unknown values
    stay None ("unknown is not zero"). Returns None when the analysis has no
    usable estimated portion weight.
    """
    if not isinstance(analysis, dict):
        return None
    nutrition = analysis.get('nutrition') or {}
    portion = analysis.get('portion') or {}
    weight = portion.get('estimated_weight_g')
    if weight is None:
        return None
    weight = Decimal(str(weight))
    if weight <= 0:
        return None
    factor = Decimal('100') / weight
    result = {}
    for source_key, target_key in (('calories_kcal', 'kcal_100g'), ('protein_g', 'protein_100g'),
                                   ('carbohydrates_g', 'carbs_100g'), ('fat_g', 'fat_100g')):
        value = nutrition.get(source_key)
        if value is None:
            result[target_key] = None
        else:
            result[target_key] = str(max(Decimal('0'), (Decimal(str(value)) * factor)
                                         .quantize(Decimal('0.1'), rounding=ROUND_HALF_UP)))
    return result


def calculate_meals_totals(meals):
    values = {'kcal': Decimal('0'), 'protein_g': Decimal('0'), 'carbs_g': Decimal('0'), 'fat_g': Decimal('0')}
    for meal in meals:
        for item in meal.items.all():
            for name in values:
                values[name] += getattr(item, name)
    return {key: str(value) for key, value in values.items()}


def refresh_daily_summary_for_meal(user, eaten_at):
    if eaten_at is None:
        return None
    tz = patient_timezone(user)
    local_date = django_timezone.localtime(eaten_at, tz).date()
    start, end = date_window(local_date.isoformat(), tz.key)
    meals = list(Meal.objects.filter(user=user, eaten_at__gte=start, eaten_at__lt=end).prefetch_related('items'))
    totals_dict = calculate_meals_totals(meals)
    summary, _ = DailyNutritionSummary.objects.update_or_create(
        user=user,
        summary_date=local_date,
        defaults={
            'meal_count': len(meals),
            'kcal': Decimal(totals_dict['kcal']),
            'protein_g': Decimal(totals_dict['protein_g']),
            'carbs_g': Decimal(totals_dict['carbs_g']),
            'fat_g': Decimal(totals_dict['fat_g']),
            'calculation_version': 'v1',
            'computed_at': django_timezone.now(),
        },
    )
    return summary


def record_food_log(user, meal, action, previous_values=None, new_values=None, meal_id_snapshot=None):
    FoodLog.objects.create(
        user=user,
        meal=meal,
        meal_id_snapshot=meal.id if meal is not None else meal_id_snapshot,
        action=action,
        previous_values=previous_values,
        new_values=new_values,
    )


@transaction.atomic
def replace_meal_items(meal: Meal, items):
    if not items:
        raise ValidationError({'items': 'Add at least one food.'})
    meal.items.all().delete()
    for item in items:
        try:
            food = Food.objects.get(Q(created_by=meal.user) | Q(created_by__isnull=True), pk=item['food_id'])
        except Food.DoesNotExist:
            raise ValidationError({'items': 'Food not found.'}) from None
        grams = Decimal(str(item['grams'])).quantize(TWO, rounding=ROUND_HALF_UP)
        if grams <= 0 or grams > 10000:
            raise ValidationError({'items': 'Serving must be between 0 and 10000 g.'})
        result = None
        serving = None
        if item.get('serving_id'):
            serving = FoodServing.objects.filter(pk=item['serving_id'], food=food).first()
            if serving is None:
                raise ValidationError({'items': 'Serving does not belong to this food.'})
        if item.get('recognition_result_id'):
            result = RecognitionResult.objects.filter(
                pk=item['recognition_result_id'], session__user=meal.user).first()
            if result is None:
                raise ValidationError({'items': 'Recognition result does not match this food.'})
            if result.session.image_id != meal.image_id:
                raise ValidationError({'items': 'Recognition result belongs to another meal image.'})
            if result.food_id != food.id:
                result.food = food
                result.save(update_fields=['food'])
        MealItem.objects.create(meal=meal, food=food, food_name=food.name, grams=grams,
                                serving=serving, recognition_result=result,
                                **nutrient_snapshot(food, grams))


def owned_image(user, image_id):
    if not image_id:
        return None
    try:
        return FoodImage.objects.get(pk=image_id, user=user, deletion_requested_at__isnull=True)
    except FoodImage.DoesNotExist:
        raise ValidationError({'image_id': 'Image not found.'}) from None


def meal_request_hash(data):
    payload = {
        'eaten_at': data['eaten_at'].isoformat(),
        'meal_type': data['meal_type'],
        'notes': data.get('notes', ''),
        'image_id': str(data.get('image_id') or ''),
        'items': [{'food_id': str(item['food_id']), 'grams': str(item['grams']),
                   'serving_id': str(item.get('serving_id') or ''),
                   'recognition_result_id': str(item.get('recognition_result_id') or '')} for item in data['items']],
    }
    return sha256(json.dumps(payload, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


@transaction.atomic
def create_meal(user, data):
    operation_id = data.get('operation_id')
    operation = None
    if operation_id:
        request_hash = meal_request_hash(data)
        operation, created = IdempotencyRecord.objects.select_for_update().get_or_create(
            user=user, operation_id=operation_id, defaults={'request_hash': request_hash})
        if not created:
            if operation.request_hash and operation.request_hash != request_hash:
                raise IdempotencyConflict()
            if operation.meal_id:
                if operation.response_snapshot:
                    return operation.meal, False, operation.response_snapshot
                from .serializers import MealSerializer
                return operation.meal, False, json.loads(json.dumps(MealSerializer(operation.meal).data, cls=DjangoJSONEncoder))
            if operation.response_snapshot:
                return None, False, operation.response_snapshot
            raise ValidationError({'operation_id': 'Meal save is still pending. Retry shortly.'})
    meal = Meal.objects.create(
        user=user, eaten_at=data['eaten_at'], meal_type=data['meal_type'],
        notes=data.get('notes', ''), image=owned_image(user, data.get('image_id')))
    replace_meal_items(meal, data['items'])
    from .serializers import MealSerializer
    response_snapshot = json.loads(json.dumps(MealSerializer(meal).data, cls=DjangoJSONEncoder))
    if operation:
        operation.meal = meal
        operation.response_snapshot = response_snapshot
        operation.save(update_fields=['meal', 'response_snapshot'])
    record_food_log(user, meal, action='created', new_values=response_snapshot)
    refresh_daily_summary_for_meal(user, meal.eaten_at)
    return meal, True, response_snapshot


@transaction.atomic
def update_meal_for_user(user, meal_id, data):
    from .serializers import MealSerializer
    meal = Meal.objects.select_for_update().prefetch_related('items').get(pk=meal_id, user=user)
    if data.get('version') != meal.version:
        return None, json.loads(json.dumps(MealSerializer(meal).data, cls=DjangoJSONEncoder))
    previous_snapshot = json.loads(json.dumps(MealSerializer(meal).data, cls=DjangoJSONEncoder))
    previous_eaten_at = meal.eaten_at
    meal.eaten_at, meal.meal_type = data['eaten_at'], data['meal_type']
    meal.notes = data.get('notes', '')
    meal.image = owned_image(user, data.get('image_id'))
    meal.version += 1
    meal.save()
    replace_meal_items(meal, data['items'])
    new_snapshot = json.loads(json.dumps(MealSerializer(meal).data, cls=DjangoJSONEncoder))
    record_food_log(user, meal, action='updated', previous_values=previous_snapshot, new_values=new_snapshot)
    refresh_daily_summary_for_meal(user, previous_eaten_at)
    refresh_daily_summary_for_meal(user, meal.eaten_at)
    return meal, new_snapshot


@transaction.atomic
def delete_meal_for_user(user, meal):
    from .serializers import MealSerializer
    previous_snapshot = json.loads(json.dumps(MealSerializer(meal).data, cls=DjangoJSONEncoder))
    meal_id_val = meal.id
    eaten_at = meal.image and meal.eaten_at or meal.eaten_at
    image = meal.image
    record_food_log(user, None, action='deleted', previous_values=previous_snapshot, meal_id_snapshot=meal_id_val)
    meal.delete()
    if image and not Meal.objects.filter(image=image).exists():
        delete_private_image(user, image.id)
    refresh_daily_summary_for_meal(user, eaten_at)


def prune_expired_records(idempotency_days=7, orphan_image_hours=24):
    now = django_timezone.now()
    idem_cutoff = now - timedelta(days=idempotency_days)
    deleted_idem, _ = IdempotencyRecord.objects.filter(created_at__lt=idem_cutoff).delete()
    img_cutoff = now - timedelta(hours=orphan_image_hours)
    orphan_images = list(
        FoodImage.objects.filter(
            created_at__lt=img_cutoff,
            meal__isnull=True,
            foodprediction__isnull=True,
        )
    )
    orphan_count = 0
    for img in orphan_images:
        if delete_private_image(img.user, img.id):
            orphan_count += 1
    return {'idempotency_records': deleted_idem, 'orphan_images': orphan_count}


GOAL_FIELDS = {
    'daily_kcal_goal': ('kcal', 'kcal'),
    'protein_goal_g': ('protein_g', 'g'),
    'carbs_goal_g': ('carbs_g', 'g'),
    'fat_goal_g': ('fat_g', 'g'),
}


def goal_values_for_user(user):
    goal = NutritionGoal.objects.filter(user=user, status='active').prefetch_related('targets').first()
    if goal is None:
        return None
    targets = {target.nutrient_name: target.target_value for target in goal.targets.all()}
    return {
        field: (int(targets[nutrient]) if nutrient in targets else None)
        for field, (nutrient, _) in GOAL_FIELDS.items()
    }


@transaction.atomic
def revise_profile_goal(profile):
    """Copy the four profile controls into a dated, versioned goal revision."""
    target_values = [(nutrient, unit, getattr(profile, field))
                     for field, (nutrient, unit) in GOAL_FIELDS.items() if getattr(profile, field) > 0]
    current = NutritionGoal.objects.select_for_update().filter(user=profile.user, status='active').first()
    if current:
        current_values = {item.nutrient_name: int(item.target_value) for item in current.targets.all()}
        if current_values == {nutrient: value for nutrient, _, value in target_values}:
            return current
    today = django_timezone.localtime(django_timezone.now(), ZoneInfo(profile.timezone)).date()
    version = (NutritionGoal.objects.filter(user=profile.user).order_by('-version')
               .values_list('version', flat=True).first() or 0) + 1
    if current:
        current.status = 'closed'
        current.effective_until = today
        current.save(update_fields=['status', 'effective_until'])
    if not target_values:
        return None
    goal = NutritionGoal.objects.create(user=profile.user, version=version, effective_from=today)
    NutrientTarget.objects.bulk_create([
        NutrientTarget(goal=goal, nutrient_name=nutrient, target_value=value, unit=unit)
        for nutrient, unit, value in target_values
    ])
    return goal


def process_media_deletion(job_id):
    job = MediaDeletionJob.objects.filter(pk=job_id, completed_at__isnull=True).first()
    if job is None:
        return
    job.attempts += 1
    try:
        FoodImage._meta.get_field('file').storage.delete(job.storage_key)
    except Exception:
        job.last_error_code = 'STORAGE_DELETE_FAILED'
        job.save(update_fields=['attempts', 'last_error_code'])
        logger.exception('Private media deletion failed for job %s', job.pk)
        return
    job.completed_at = django_timezone.now()
    job.last_error_code = ''
    job.save(update_fields=['attempts', 'completed_at', 'last_error_code'])


def queue_media_deletion(storage_key):
    if not storage_key:
        return
    job, _ = MediaDeletionJob.objects.get_or_create(storage_key=storage_key)
    transaction.on_commit(lambda job_id=job.pk: process_media_deletion(job_id))


@transaction.atomic
def delete_private_image(user, image_id):
    image = FoodImage.objects.select_for_update().filter(pk=image_id, user=user).first()
    if image is None:
        return False
    Meal.objects.filter(user=user, image=image).update(image=None)
    FoodPrediction.objects.filter(user=user, image=image).delete()
    queue_media_deletion(image.file.name)
    image.delete()
    return True


@transaction.atomic
def delete_user_with_media(user):
    for storage_key in FoodImage.objects.filter(user=user).values_list('file', flat=True):
        queue_media_deletion(storage_key)
    profile = getattr(user, 'profile', None)
    if profile and profile.profile_picture:
        queue_media_deletion(profile.profile_picture.name)
    # Private foods are removed with the account. Their versioned records use
    # PROTECT for catalogue safety, so release only this user's private rows.
    private_records = NutritionRecord.objects.filter(food__created_by=user)
    FoodNutrition.objects.filter(food__created_by=user).delete()
    private_records.delete()
    user.delete()


def date_window(date_text, timezone_name):
    date = parse_date(date_text or '')
    if date is None:
        raise ValidationError({'date': 'Use YYYY-MM-DD.'})
    try:
        tz = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        tz = timezone.utc
    start = datetime.combine(date, time.min, tzinfo=tz)
    return start.astimezone(timezone.utc), (start + timedelta(days=1)).astimezone(timezone.utc)


# --- Doctor meal-history access ---
# Doctors have no accounts: a patient approves a request, then the request's
# view token grants read-only history/analytics for a bounded window.
DOCTOR_ACCESS_HOURS = 72
DOCTOR_ANALYTICS_MAX_DAYS = 366
DOCTOR_HISTORY_MAX_LIMIT = 500
# Identical for matched and unmatched identifiers so the public page cannot be
# used to confirm whether an email or phone has a MealSense account.
DOCTOR_REQUEST_PENDING_MESSAGE = (
    'If the patient has a MealSense account, your request appears in their app '
    'for approval. Double-check the email or phone if nothing arrives.'
)
_EMAIL_PATTERN = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')
_PHONE_PATTERN = re.compile(r'^\d{6,15}$')


def normalize_phone(raw_value):
    digits = re.sub(r'\D', '', str(raw_value or ''))
    if not _PHONE_PATTERN.fullmatch(digits):
        raise ValidationError({'identifier': 'Enter a valid email address or phone number.'})
    return digits


def resolve_patient(identifier):
    """Return (identifier_type, normalized_identifier, patient_user_or_None)."""
    text = str(identifier or '').strip()
    if '@' in text:
        if len(text) > 254 or not _EMAIL_PATTERN.fullmatch(text):
            raise ValidationError({'identifier': 'Enter a valid email address or phone number.'})
        email = text.lower()
        return 'email', email, User.objects.filter(email__iexact=email).first()
    digits = normalize_phone(text)
    profile = Profile.objects.filter(phone=digits).select_related('user').first()
    return 'phone', digits, profile.user if profile else None


def patient_zone(timezone_name):
    try:
        return ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        return timezone.utc


def patient_timezone(user):
    name = Profile.objects.filter(user=user).values_list('timezone', flat=True).first()
    return patient_zone(name or 'UTC')


def create_doctor_access_request(patient, doctor_name, identifier_type, identifier):
    """Create or reuse a pending request; returns (request, created)."""
    doctor_name = str(doctor_name).strip()[:120]
    with transaction.atomic():
        existing = (DoctorAccessRequest.objects.select_for_update()
                    .filter(patient=patient, identifier_type=identifier_type, identifier=identifier,
                            status=DoctorAccessRequest.STATUS_PENDING, doctor_name__iexact=doctor_name)
                    .order_by('-created_at').first())
        if existing:
            return existing, False
        request = DoctorAccessRequest.objects.create(
            patient=patient, doctor_name=doctor_name,
            identifier_type=identifier_type, identifier=identifier)
        return request, True


def doctor_request_for_token(token):
    if not token:
        return None
    clean = str(token).strip()
    if not (16 <= len(clean) <= 64):
        return None
    req = (DoctorAccessRequest.objects.filter(view_token=clean)
           .select_related('patient').first())
    if req is None or not secrets.compare_digest(req.view_token, clean):
        return None
    return req


@transaction.atomic
def decide_doctor_access_request(access_request, action, user):
    """Apply an approve/deny/revoke decision made by the patient in their app."""
    locked = DoctorAccessRequest.objects.select_for_update().get(pk=access_request.pk, patient=user)
    now = django_timezone.now()
    expired = locked.status == DoctorAccessRequest.STATUS_APPROVED and not locked.is_active()
    if action == 'approve':
        if locked.status not in (DoctorAccessRequest.STATUS_PENDING, DoctorAccessRequest.STATUS_DENIED,
                                 DoctorAccessRequest.STATUS_REVOKED) and not expired:
            raise ValidationError({'action': 'This request can no longer be approved.'})
        was_revoked = locked.status == DoctorAccessRequest.STATUS_REVOKED
        locked.status = DoctorAccessRequest.STATUS_APPROVED
        locked.approved_at = now
        locked.denied_at = None
        locked.revoked_at = None
        locked.expires_at = now + timedelta(hours=DOCTOR_ACCESS_HOURS)
        if was_revoked:
            # A revoked share must never come back to life with its old token:
            # rotation invalidates every copy the doctor received before, so a
            # leaked token cannot be resurrected by re-approval. To regain
            # access, the doctor requests it again and receives the new token
            # in the creation response.
            locked.view_token = generate_doctor_access_token()
    elif action == 'deny':
        if locked.status != DoctorAccessRequest.STATUS_PENDING:
            raise ValidationError({'action': 'Only a pending request can be denied.'})
        locked.status = DoctorAccessRequest.STATUS_DENIED
        locked.denied_at = now
        locked.expires_at = None
    elif action == 'revoke':
        if locked.status != DoctorAccessRequest.STATUS_APPROVED or not locked.is_active():
            raise ValidationError({'action': 'Only an active share can be revoked.'})
        locked.status = DoctorAccessRequest.STATUS_REVOKED
        locked.revoked_at = now
        locked.expires_at = now
    else:
        raise ValidationError({'action': 'Choose approve, deny, or revoke.'})
    locked.save()
    return locked


def doctor_request_status_payload(access_request):
    data = {'status': access_request.effective_status(), 'active': access_request.is_active(),
            'created_at': access_request.created_at}
    if access_request.is_active():
        patient = access_request.patient
        data.update({
            'patient_name': patient.display_name or patient.username,
            'patient_timezone': patient_timezone(patient).key,
            'approved_at': access_request.approved_at,
            'expires_at': access_request.expires_at,
        })
    return data


def _dec(value):
    return value if isinstance(value, Decimal) else Decimal('0')


def doctor_meal_payload(meal, tz):
    items = list(meal.items.all())
    totals = {
        'kcal': sum((_dec(item.kcal) for item in items), Decimal('0')),
        'protein_g': sum((_dec(item.protein_g) for item in items), Decimal('0')),
        'carbs_g': sum((_dec(item.carbs_g) for item in items), Decimal('0')),
        'fat_g': sum((_dec(item.fat_g) for item in items), Decimal('0')),
    }
    local = django_timezone.localtime(meal.eaten_at, tz)
    return {
        'id': str(meal.id),
        'eaten_at': meal.eaten_at,
        'local_date': local.date().isoformat(),
        'meal_type': meal.meal_type,
        # Photos, notes, and health metrics are never shared with doctors.
        'items': [{'food_name': item.food_name, 'grams': str(item.grams), 'kcal': str(item.kcal),
                   'protein_g': str(item.protein_g), 'carbs_g': str(item.carbs_g), 'fat_g': str(item.fat_g),
                   'nutrition_source_snapshot': item.nutrition_source_snapshot}
                  for item in items],
        'totals': {name: str(value) for name, value in totals.items()},
    }


def date_range_window(from_text=None, to_text=None, timezone_name='UTC', max_days=None):
    """UTC [start, end) window for an inclusive local from/to date range."""
    from_date = parse_date(from_text) if from_text else None
    to_date = parse_date(to_text) if to_text else None
    if (from_text and from_date is None) or (to_text and to_date is None):
        raise ValidationError({'range': 'Use YYYY-MM-DD dates.'})
    if from_date is None:
        from_date = date(2000, 1, 1)
    if to_date is None:
        to_date = django_timezone.localtime(django_timezone.now(), patient_zone(timezone_name)).date()
    if to_date < from_date:
        raise ValidationError({'range': 'The end date must be on or after the start date.'})
    if max_days is not None and from_text and to_text and (to_date - from_date).days > max_days:
        raise ValidationError({'range': f'Choose a range of up to {max_days} days.'})
    tz = patient_zone(timezone_name)
    start = datetime.combine(from_date, time.min, tzinfo=tz).astimezone(timezone.utc)
    end = datetime.combine(to_date + timedelta(days=1), time.min, tzinfo=tz).astimezone(timezone.utc)
    return start, end, from_date, to_date


def doctor_meal_history(user, start, end, tz, limit=100, offset=0):
    meals = (Meal.objects.filter(user=user, eaten_at__gte=start, eaten_at__lt=end)
             .prefetch_related('items').order_by('-eaten_at'))
    return {
        'count': meals.count(),
        'limit': limit,
        'offset': offset,
        'meals': [doctor_meal_payload(meal, tz) for meal in meals[offset:offset + limit]],
    }


def doctor_analytics(user, start, end, tz):
    """Aggregate food frequency, monthly, and daily data from meal snapshots."""
    item_qs = MealItem.objects.filter(meal__user=user, meal__eaten_at__gte=start, meal__eaten_at__lt=end)
    meal_qs = Meal.objects.filter(user=user, eaten_at__gte=start, eaten_at__lt=end)

    totals = item_qs.aggregate(
        items=Count('id'), grams=Sum('grams'), kcal=Sum('kcal'),
        protein_g=Sum('protein_g'), carbs_g=Sum('carbs_g'), fat_g=Sum('fat_g'))
    meals_logged = meal_qs.count()

    most_consumed = list(item_qs.values('food_name').annotate(
        times=Count('id'), grams=Sum('grams'), kcal=Sum('kcal'),
        protein_g=Sum('protein_g'), carbs_g=Sum('carbs_g'), fat_g=Sum('fat_g'),
    ).order_by('-grams', 'food_name')[:10])

    food_frequency = list(item_qs.values('food_name').annotate(
        times=Count('id'), grams=Sum('grams'), kcal=Sum('kcal'),
    ).order_by('-times', 'food_name')[:500])

    monthly = list(meal_qs.annotate(month=TruncMonth('eaten_at', tzinfo=tz)).values('month').annotate(
        meals=Count('id', distinct=True), item_count=Count('items__id'),
        kcal=Sum('items__kcal'), protein_g=Sum('items__protein_g'),
        carbs_g=Sum('items__carbs_g'), fat_g=Sum('items__fat_g'), grams=Sum('items__grams'),
    ).order_by('month'))

    daily = list(meal_qs.annotate(day=TruncDay('eaten_at', tzinfo=tz)).values('day').annotate(
        meals=Count('id', distinct=True), item_count=Count('items__id'),
        kcal=Sum('items__kcal'), protein_g=Sum('items__protein_g'),
        carbs_g=Sum('items__carbs_g'), fat_g=Sum('items__fat_g'), grams=Sum('items__grams'),
    ).order_by('day'))

    by_meal_type = list(meal_qs.values('meal_type').annotate(
        meals=Count('id', distinct=True), item_count=Count('items__id'),
        kcal=Sum('items__kcal'), grams=Sum('items__grams'),
    ).order_by('meal_type'))

    logged_days = len(daily)
    total_kcal = _dec(totals['kcal'])
    average = (total_kcal / logged_days).quantize(Decimal('1'), rounding=ROUND_HALF_UP) if logged_days else Decimal('0')

    def bucket(row, key):
        value = row[key]
        text = value.strftime('%Y-%m' if key == 'month' else '%Y-%m-%d') if value is not None else ''
        return {
            key: text,
            'meals': row['meals'], 'item_count': row['item_count'],
            'kcal': str(_dec(row['kcal'])), 'protein_g': str(_dec(row['protein_g'])),
            'carbs_g': str(_dec(row['carbs_g'])), 'fat_g': str(_dec(row['fat_g'])),
            'grams': str(_dec(row['grams'])),
        }

    return {
        'totals': {'items': totals['items'] or 0, 'kcal': str(total_kcal),
                   'protein_g': str(_dec(totals['protein_g'])), 'carbs_g': str(_dec(totals['carbs_g'])),
                   'fat_g': str(_dec(totals['fat_g'])), 'grams': str(_dec(totals['grams']))},
        'meals_logged': meals_logged,
        'items_logged': totals['items'] or 0,
        'logged_days': logged_days,
        'avg_kcal_per_logged_day': str(average),
        'most_consumed': [{'food_name': row['food_name'], 'times': row['times'],
                           'grams': str(_dec(row['grams'])), 'kcal': str(_dec(row['kcal'])),
                           'protein_g': str(_dec(row['protein_g'])), 'carbs_g': str(_dec(row['carbs_g'])),
                           'fat_g': str(_dec(row['fat_g']))} for row in most_consumed],
        'food_frequency': [{'food_name': row['food_name'], 'times': row['times'],
                            'grams': str(_dec(row['grams'])), 'kcal': str(_dec(row['kcal']))}
                           for row in food_frequency],
        'monthly': [bucket(row, 'month') for row in monthly],
        'daily': [bucket(row, 'day') for row in daily],
        'by_meal_type': [{'meal_type': row['meal_type'], 'meals': row['meals'], 'item_count': row['item_count'],
                          'kcal': str(_dec(row['kcal'])), 'grams': str(_dec(row['grams']))}
                         for row in by_meal_type],
    }
