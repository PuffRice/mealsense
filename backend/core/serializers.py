from datetime import date
from decimal import Decimal, InvalidOperation
from uuid import UUID
from rest_framework import serializers
from .models import Food, Meal, MealItem, Profile

VALID_GENDERS = ('', 'male', 'female', 'other')


class ProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = Profile
        fields = [
            'timezone',
            'units',
            'gender',
            'date_of_birth',
            'height_cm',
            'weight_kg',
            'daily_kcal_goal',
            'protein_goal_g',
            'carbs_goal_g',
            'fat_goal_g',
        ]

    def validate_gender(self, value):
        normalized = str(value or '').strip().lower()
        if normalized not in VALID_GENDERS:
            raise serializers.ValidationError('Select a valid gender.')
        return normalized

    def validate_date_of_birth(self, value):
        if value and value > date.today():
            raise serializers.ValidationError('Date of birth cannot be in the future.')
        return value


class FoodSerializer(serializers.ModelSerializer):
    servings = serializers.SerializerMethodField()

    class Meta:
        model = Food
        fields = ['id', 'name', 'name_bn', 'category', 'kcal_100g', 'protein_100g', 'carbs_100g', 'fat_100g',
                  'source', 'source_ref', 'is_sample', 'is_verified', 'servings']
        read_only_fields = ['id', 'is_sample', 'is_verified', 'servings']

    def get_servings(self, instance):
        return [{'id': serving.id, 'name': serving.name, 'name_bn': serving.name_bn,
                 'definition': serving.definition, 'weight_g': str(serving.weight_g),
                 'preparation_state': serving.preparation_state,
                 'is_approximate': serving.is_approximate, 'is_default': serving.is_default}
                for serving in instance.servings.all()]

    def to_representation(self, instance):
        result = super().to_representation(instance)
        pointer = getattr(instance, 'current_nutrition', None)
        if pointer:
            record = pointer.active_record
            factor = Decimal('100') / record.basis_quantity
            for name, field in (('kcal', 'kcal_100g'), ('protein_g', 'protein_100g'),
                                ('carbs_g', 'carbs_100g'), ('fat_g', 'fat_100g')):
                value = record.nutrient_values.get(name)
                result[field] = str((Decimal(str(value)) * factor).quantize(Decimal('0.01'))) if value is not None else None
            result['source'] = record.source.name
            result['source_ref'] = record.source.reference
        return result


class MealItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = MealItem
        fields = ['id', 'food', 'food_name', 'grams', 'serving', 'kcal', 'protein_g', 'carbs_g', 'fat_g',
                  'recognition_result', 'nutrition_source_snapshot', 'nutrition_basis_snapshot', 'calculation_version']


class MealSerializer(serializers.ModelSerializer):
    items = MealItemSerializer(many=True, read_only=True)
    totals = serializers.SerializerMethodField()

    class Meta:
        model = Meal
        fields = ['id', 'eaten_at', 'meal_type', 'notes', 'version', 'image', 'items', 'totals']

    def get_totals(self, obj):
        items = list(obj.items.all())
        return {name: str(sum((getattr(item, name) for item in items), Decimal('0')))
                for name in ['kcal', 'protein_g', 'carbs_g', 'fat_g']}


class MealInputSerializer(serializers.Serializer):
    eaten_at = serializers.DateTimeField()
    meal_type = serializers.ChoiceField(choices=['breakfast', 'lunch', 'dinner', 'snack'])
    notes = serializers.CharField(allow_blank=True, required=False, max_length=1000)
    image_id = serializers.UUIDField(required=False, allow_null=True)
    items = serializers.ListField(child=serializers.DictField(), min_length=1)
    version = serializers.IntegerField(required=False, min_value=1)
    operation_id = serializers.UUIDField(required=False)

    def validate_items(self, values):
        if len(values) > 30:
            raise serializers.ValidationError('Too many items.')
        for item in values:
            if 'food_id' not in item or 'grams' not in item:
                raise serializers.ValidationError('Each item needs food_id and grams.')
            try:
                UUID(str(item['food_id']))
                if item.get('serving_id'):
                    if int(item['serving_id']) <= 0:
                        raise ValueError()
                if item.get('recognition_result_id'):
                    UUID(str(item['recognition_result_id']))
                grams = Decimal(str(item['grams']))
                if not grams.is_finite() or grams <= 0 or grams > 10000:
                    raise ValueError()
            except (ValueError, TypeError, InvalidOperation):
                raise serializers.ValidationError('Invalid serving grams.') from None
        return values
