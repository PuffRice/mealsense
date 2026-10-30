from decimal import Decimal, InvalidOperation
from uuid import UUID
from rest_framework import serializers
from .models import Food, Meal, MealItem, Profile


class ProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = Profile
        fields = ['timezone', 'units', 'daily_kcal_goal', 'protein_goal_g', 'carbs_goal_g', 'fat_goal_g']


class FoodSerializer(serializers.ModelSerializer):
    class Meta:
        model = Food
        fields = ['id', 'name', 'category', 'kcal_100g', 'protein_100g', 'carbs_100g', 'fat_100g', 'source', 'source_ref', 'is_sample']
        read_only_fields = ['id', 'is_sample']


class MealItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = MealItem
        fields = ['id', 'food', 'food_name', 'grams', 'kcal', 'protein_g', 'carbs_g', 'fat_g']


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
                grams = Decimal(str(item['grams']))
                if not grams.is_finite() or grams <= 0 or grams > 10000:
                    raise ValueError()
            except (ValueError, TypeError, InvalidOperation):
                raise serializers.ValidationError('Invalid serving grams.') from None
        return values
