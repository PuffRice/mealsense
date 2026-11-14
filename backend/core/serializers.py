from datetime import date
from decimal import Decimal, InvalidOperation
from uuid import UUID
from rest_framework import serializers
from .models import DoctorAccessRequest, Food, Meal, MealItem, Profile

VALID_GENDERS = ('', 'male', 'female', 'other')


class ProfileSerializer(serializers.ModelSerializer):
    profile_picture = serializers.ImageField(
        write_only=True,
        required=False,
        allow_null=True,
    )
    profile_picture_url = serializers.SerializerMethodField()

    class Meta:
        model = Profile
        fields = [
            'profile_picture_url',
            'profile_picture',
            'timezone',
            'units',
            'phone',
            'gender',
            'date_of_birth',
            'height_cm',
            'weight_kg',
            'daily_kcal_goal',
            'protein_goal_g',
            'carbs_goal_g',
            'fat_goal_g',
        ]
        read_only_fields = ['profile_picture_url']

    def get_profile_picture_url(self, instance):
        if not instance.profile_picture:
            return None
        request = self.context.get('request')
        path = '/api/v1/users/me/profile-picture/'
        return request.build_absolute_uri(path) if request else path

    def validate_phone(self, value):
        # Store NULL when unset so the unique constraint allows many missing values.
        if not str(value or '').strip():
            return None
        from .services import normalize_phone
        return normalize_phone(value)

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


class DoctorAccessRequestSerializer(serializers.ModelSerializer):
    """Patient-facing representation; the view token is never exposed here."""

    class Meta:
        model = DoctorAccessRequest
        fields = ['id', 'doctor_name', 'identifier_type', 'identifier', 'status',
                  'created_at', 'approved_at', 'expires_at', 'denied_at', 'revoked_at']


class StructuredIngredientSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=160)
    estimated_weight_g = serializers.FloatField(min_value=0.0)
    ingredient_key = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    identification = serializers.ChoiceField(
        choices=['visible', 'recipe_inferred'], required=False, allow_null=True
    )
    confidence = serializers.FloatField(required=False, allow_null=True)
    nutrition_source = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    recipe_source = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    calories_kcal = serializers.FloatField(required=False, allow_null=True)
    protein_g = serializers.FloatField(required=False, allow_null=True)
    carbohydrates_g = serializers.FloatField(required=False, allow_null=True)
    fat_g = serializers.FloatField(required=False, allow_null=True)


class StructuredNutritionAnalysisSerializer(serializers.Serializer):
    food_name = serializers.CharField(max_length=160)
    canonical_catalog_name = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    food_class = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    classification = serializers.DictField()
    portion = serializers.DictField()
    ingredients = StructuredIngredientSerializer(many=True)
    nutrition = serializers.DictField()
    micronutrients = serializers.DictField()
    confidence = serializers.DictField()
    provenance = serializers.DictField(required=False)
    observed_preparation_state = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    occluded_or_uncertain = serializers.BooleanField(required=False, default=False)
    requires_user_confirmation = serializers.BooleanField(required=False, default=True)
    warnings = serializers.ListField(child=serializers.CharField(), required=False, default=list)
    explanation = serializers.CharField()
    vlm_checkpoint = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    timing = serializers.DictField(required=False)


class AnalyzedMealSaveSerializer(serializers.Serializer):
    eaten_at = serializers.DateTimeField(required=False)
    meal_type = serializers.ChoiceField(choices=['breakfast', 'lunch', 'dinner', 'snack'], default='lunch')
    notes = serializers.CharField(allow_blank=True, required=False, max_length=1000, default='')
    portion_weight_g = serializers.DecimalField(
        max_digits=8, decimal_places=2, required=False, min_value=Decimal('1'), max_value=Decimal('10000')
    )
    save_mode = serializers.ChoiceField(choices=['ingredients', 'dish'], default='ingredients')
    operation_id = serializers.UUIDField(required=False)


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
                if item.get('serving_id') not in (None, ''):
                    if int(str(item['serving_id'])) <= 0:
                        raise ValueError()
                if item.get('recognition_result_id') not in (None, ''):
                    raw_result_id = str(item['recognition_result_id']).strip()
                    if raw_result_id.isdigit():
                        if int(raw_result_id) <= 0:
                            raise ValueError()
                    else:
                        UUID(raw_result_id)
                grams = Decimal(str(item['grams']))
                if not grams.is_finite() or grams <= 0 or grams > 10000:
                    raise ValueError()
            except (ValueError, TypeError, InvalidOperation):
                raise serializers.ValidationError('Invalid serving grams.') from None
        return values
