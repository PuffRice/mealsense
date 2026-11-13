from decimal import Decimal, ROUND_HALF_UP
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from datetime import date, datetime, time, timedelta, timezone
import base64
import json
import logging
import re
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
from .models import (DoctorAccessRequest, Food, FoodImage, FoodNutrition, FoodPrediction, FoodServing,
                     IdempotencyRecord, Meal, MealItem, MediaDeletionJob,
                     NutrientTarget, NutritionGoal, NutritionRecord,
                     Profile, RecognitionResult, User)
from .recognition_labels import model_search_names

logger = logging.getLogger(__name__)

TWO = Decimal('0.01')

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

    Returns {'status', 'candidates', 'model_version', 'error_code'} and never
    raises for normal inference failures; missing/unapproved config counts as
    unavailable so callers fall back to manual logging.
    """
    provider = getattr(settings, 'AI_PROVIDER', '')
    if provider == 'dinov3':
        from .dinov3_recognition import recognize_dinov3
        return recognize_dinov3(image_bytes)
    if provider == 'local':
        from .local_recognition import recognize_locally
        return recognize_locally(image_bytes)
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
        # Legacy values remain usable until a reviewer selects an approved
        # record. A newly imported draft must never silently become current.
        record = (NutritionRecord.objects.filter(food=food, version=1)
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
    return (DoctorAccessRequest.objects.filter(view_token=str(token).strip()[:64])
            .select_related('patient').first())


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
        locked.status = DoctorAccessRequest.STATUS_APPROVED
        locked.approved_at = now
        locked.denied_at = None
        locked.revoked_at = None
        locked.expires_at = now + timedelta(hours=DOCTOR_ACCESS_HOURS)
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
