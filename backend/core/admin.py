from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import (
    Food,
    FoodImage,
    FoodPrediction,
    IdempotencyRecord,
    Meal,
    MealItem,
    Profile,
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
