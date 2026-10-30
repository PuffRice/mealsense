from decimal import Decimal, ROUND_HALF_UP
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from datetime import datetime, time, timedelta, timezone
from django.db import transaction
from django.db.models import Q
from django.utils.dateparse import parse_date
from rest_framework.exceptions import ValidationError
from .models import Food, Meal, MealItem

TWO = Decimal('0.01')


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
