from decimal import Decimal, ROUND_HALF_UP
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from datetime import datetime, time, timedelta, timezone
import base64
import json
import logging
import urllib.error
import urllib.request
from io import BytesIO
from hashlib import sha256

from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.db.models import Q
from django.utils import timezone as django_timezone
from django.utils.dateparse import parse_date
from rest_framework.exceptions import ValidationError
from rest_framework.exceptions import APIException
from .models import (Food, FoodImage, FoodNutrition, FoodPrediction, FoodServing,
                     IdempotencyRecord, Meal, MealItem, MediaDeletionJob,
                     NutrientTarget, NutritionGoal, NutritionRecord,
                     RecognitionResult)

logger = logging.getLogger(__name__)

TWO = Decimal('0.01')

# --- Temporary cloud recognition adapters (swap for the in-house model later) ---
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
    """Single switch point for cloud recognition.

    Returns {'status', 'candidates', 'model_version', 'error_code'} and never
    raises for normal cloud failures; missing/unapproved config counts as
    unavailable so callers fall back to manual logging.
    """
    provider = getattr(settings, 'AI_PROVIDER', '')
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
    return {'status': 'completed',
            'candidates': [dict(candidate, food_id=None) for candidate in candidates],
            'model_version': '%s:%s' % (provider, model), 'error_code': ''}


def matched_catalog_foods(candidates, user):
    """Map candidate names to existing catalogue foods the user may pick."""
    result = {}
    for candidate in candidates:
        words = [word for word in candidate['name'].replace('-', ' ').split() if len(word) > 2]
        phrases = [' '.join(words)] + [' '.join(words[index:index + 2]) for index in range(max(0, len(words) - 1))]
        food = None
        for phrase in phrases:
            if not phrase:
                continue
            food = Food.objects.filter(Q(created_by=user) | Q(created_by__isnull=True),
                                       is_active=True).filter(
                                           Q(name__icontains=phrase) | Q(name_bn__icontains=phrase) |
                                           Q(aliases__alias__icontains=phrase)).distinct().first()
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
        # Legacy values remain usable until a reviewer selects an approved
        # record. A newly imported draft must never silently become current.
        record = (NutritionRecord.objects.filter(food=food, version=1)
                  .select_related('source').first())
    values = record.nutrient_values if record else {
        'kcal': str(food.kcal_100g), 'protein_g': str(food.protein_100g),
        'carbs_g': str(food.carbs_100g), 'fat_g': str(food.fat_100g),
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
            if result is None or (result.food_id and result.food_id != food.id):
                raise ValidationError({'items': 'Recognition result does not match this food.'})
            if result.session.image_id != meal.image_id:
                raise ValidationError({'items': 'Recognition result belongs to another meal image.'})
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
    return meal, True, response_snapshot


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
    return {field: int(targets.get(nutrient, 0)) for field, (nutrient, _) in GOAL_FIELDS.items()}


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
