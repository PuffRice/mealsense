from decimal import Decimal, ROUND_HALF_UP
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from datetime import datetime, time, timedelta, timezone
import base64
import json
import logging
import urllib.error
import urllib.request
from io import BytesIO

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils.dateparse import parse_date
from rest_framework.exceptions import ValidationError
from .models import Food, Meal, MealItem

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
                                       name__icontains=phrase).first()
            if food:
                break
        if food:
            result[candidate['name']] = str(food.id)
    return result



def nutrient_snapshot(food: Food, grams: Decimal):
    factor = grams / Decimal('100')
    return {
        'kcal': (food.kcal_100g * factor).quantize(TWO, rounding=ROUND_HALF_UP),
        'protein_g': (food.protein_100g * factor).quantize(TWO, rounding=ROUND_HALF_UP),
        'carbs_g': (food.carbs_100g * factor).quantize(TWO, rounding=ROUND_HALF_UP),
        'fat_g': (food.fat_100g * factor).quantize(TWO, rounding=ROUND_HALF_UP),
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
        MealItem.objects.create(meal=meal, food=food, food_name=food.name, grams=grams,
                                **nutrient_snapshot(food, grams))


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
