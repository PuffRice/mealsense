from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import (
    Food,
    FoodAlias,
    FoodImage,
    FoodNutrition,
    FoodPrediction,
    FoodServing,
    GoalProgress,
    IdempotencyRecord,
    Meal,
    MealItem,
    MediaDeletionJob,
    NutrientTarget,
    NutritionGoal,
    NutritionRecord,
    NutritionSource,
    Profile,
    RecognitionResult,
    User,
)


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ('email', 'display_name', 'is_staff', 'is_active', 'date_joined')
    list_filter = ('is_staff', 'is_active', 'date_joined')
    search_fields = ('email', 'display_name')
    ordering = ('-date_joined',)
    readonly_fields = ('last_login', 'date_joined')
    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Profile', {'fields': ('display_name',)}),
        ('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Dates', {'fields': ('last_login', 'date_joined')}),
    )
    add_fieldsets = ((None, {'classes': ('wide',), 'fields': ('email', 'password1', 'password2')}),)
    filter_horizontal = ('groups', 'user_permissions')


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'gender', 'date_of_birth', 'height_cm', 'weight_kg', 'timezone', 'units', 'daily_kcal_goal')
    search_fields = ('user__email',)
    list_filter = ('units', 'gender')


@admin.register(Food)
class FoodAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'kcal_100g', 'protein_100g', 'carbs_100g', 'fat_100g', 'source', 'is_sample')
    list_filter = ('category', 'source', 'is_sample')
    search_fields = ('name', 'source')


@admin.register(FoodImage)
class FoodImageAdmin(admin.ModelAdmin):
    list_display = ('user', 'mime_type', 'size_bytes', 'created_at')
    search_fields = ('user__email',)
    list_filter = ('mime_type',)
    readonly_fields = ('created_at',)
    raw_id_fields = ('user',)


@admin.register(FoodPrediction)
class FoodPredictionAdmin(admin.ModelAdmin):
    list_display = ('user', 'image', 'status', 'model_version', 'error_code', 'created_at')
    search_fields = ('user__email',)
    list_filter = ('status',)
    readonly_fields = ('created_at',)
    raw_id_fields = ('user', 'image')


class MealItemInline(admin.TabularInline):
    model = MealItem
    extra = 0
    autocomplete_fields = ('food',)


@admin.register(Meal)
class MealAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'meal_type', 'eaten_at', 'version', 'created_at')
    search_fields = ('user__email', 'id')
    list_filter = ('meal_type',)
    date_hierarchy = 'eaten_at'
    readonly_fields = ('created_at', 'updated_at')
    inlines = (MealItemInline,)
    raw_id_fields = ('user', 'image')


@admin.register(MealItem)
class MealItemAdmin(admin.ModelAdmin):
    list_display = ('meal', 'food_name', 'grams', 'kcal', 'protein_g', 'carbs_g', 'fat_g')
    search_fields = ('food_name', 'meal__user__email')
    raw_id_fields = ('meal', 'food')


@admin.register(IdempotencyRecord)
class IdempotencyRecordAdmin(admin.ModelAdmin):
    list_display = ('user', 'operation_id', 'meal')
    search_fields = ('user__email', 'operation_id')
    raw_id_fields = ('user', 'meal')


@admin.register(FoodAlias)
class FoodAliasAdmin(admin.ModelAdmin):
    list_display = ('alias', 'food', 'language', 'region', 'is_verified')
    search_fields = ('alias', 'food__name')
    raw_id_fields = ('food',)


@admin.register(FoodServing)
class FoodServingAdmin(admin.ModelAdmin):
    list_display = ('name', 'food', 'weight_g', 'preparation_state', 'is_default')
    search_fields = ('name', 'food__name')
    raw_id_fields = ('food',)


@admin.register(NutritionSource)
class NutritionSourceAdmin(admin.ModelAdmin):
    list_display = ('name', 'reference', 'is_trusted', 'retrieved_at')
    search_fields = ('name', 'reference')


@admin.register(NutritionRecord)
class NutritionRecordAdmin(admin.ModelAdmin):
    list_display = ('food', 'version', 'source', 'verification_status', 'basis_quantity', 'basis_unit')
    list_filter = ('verification_status', 'basis_unit')
    search_fields = ('food__name', 'source__name')
    raw_id_fields = ('food', 'source')
    readonly_fields = ('created_at',)

    def has_change_permission(self, request, obj=None):
        if obj and FoodNutrition.objects.filter(active_record=obj).exists():
            return False
        return super().has_change_permission(request, obj)


@admin.register(FoodNutrition)
class FoodNutritionAdmin(admin.ModelAdmin):
    list_display = ('food', 'active_record', 'updated_at')
    raw_id_fields = ('food', 'active_record')
    readonly_fields = ('updated_at',)


@admin.register(RecognitionResult)
class RecognitionResultAdmin(admin.ModelAdmin):
    list_display = ('session', 'rank', 'original_label', 'food', 'confidence')
    raw_id_fields = ('session', 'detection', 'food')


@admin.register(NutritionGoal)
class NutritionGoalAdmin(admin.ModelAdmin):
    list_display = ('user', 'version', 'status', 'effective_from', 'effective_until')
    raw_id_fields = ('user',)


@admin.register(NutrientTarget)
class NutrientTargetAdmin(admin.ModelAdmin):
    list_display = ('goal', 'nutrient_name', 'target_value', 'unit', 'target_type')
    raw_id_fields = ('goal',)


@admin.register(GoalProgress)
class GoalProgressAdmin(admin.ModelAdmin):
    list_display = ('goal', 'target', 'progress_date', 'actual_value', 'target_value')
    raw_id_fields = ('goal', 'target')


@admin.register(MediaDeletionJob)
class MediaDeletionJobAdmin(admin.ModelAdmin):
    list_display = ('storage_key', 'attempts', 'requested_at', 'completed_at', 'last_error_code')
    readonly_fields = ('storage_key', 'attempts', 'requested_at', 'completed_at', 'last_error_code')
