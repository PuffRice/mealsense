import uuid
from django.contrib.auth.base_user import BaseUserManager
from django.contrib.auth.models import AbstractUser
from django.core.validators import MinValueValidator
from django.db import models


def key():
    return uuid.uuid4()


class UserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra):
        if not email:
            raise ValueError('Email is required')
        user = self.model(email=self.normalize_email(email).lower(), **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra):
        extra.update(is_staff=True, is_superuser=True)
        return self.create_user(email, password, **extra)


class User(AbstractUser):
    id = models.UUIDField(primary_key=True, default=key, editable=False)
    username = None
    email = models.EmailField(unique=True)
    display_name = models.CharField(max_length=80, blank=True)
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []
    objects = UserManager()


class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    timezone = models.CharField(max_length=64, default='Asia/Dhaka')
    units = models.CharField(max_length=12, default='metric')
    gender = models.CharField(max_length=20, blank=True, default='')
    date_of_birth = models.DateField(null=True, blank=True)
    height_cm = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True, validators=[MinValueValidator(0)])
    weight_kg = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True, validators=[MinValueValidator(0)])
    daily_kcal_goal = models.PositiveIntegerField(default=0)
    protein_goal_g = models.PositiveIntegerField(default=0)
    carbs_goal_g = models.PositiveIntegerField(default=0)
    fat_goal_g = models.PositiveIntegerField(default=0)


class Food(models.Model):
    id = models.UUIDField(primary_key=True, default=key, editable=False)
    created_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.CASCADE)
    name = models.CharField(max_length=120)
    category = models.CharField(max_length=60, blank=True)
    kcal_100g = models.DecimalField(max_digits=8, decimal_places=2, validators=[MinValueValidator(0)])
    protein_100g = models.DecimalField(max_digits=8, decimal_places=2, validators=[MinValueValidator(0)])
    carbs_100g = models.DecimalField(max_digits=8, decimal_places=2, validators=[MinValueValidator(0)])
    fat_100g = models.DecimalField(max_digits=8, decimal_places=2, validators=[MinValueValidator(0)])
    source = models.CharField(max_length=160)
    source_ref = models.CharField(max_length=250, blank=True)
    is_sample = models.BooleanField(default=False)

    class Meta:
        ordering = ['name']


class FoodImage(models.Model):
    id = models.UUIDField(primary_key=True, default=key, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    file = models.ImageField(upload_to='meal_images/%Y/%m/%d')
    mime_type = models.CharField(max_length=40)
    size_bytes = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)


class FoodPrediction(models.Model):
    id = models.UUIDField(primary_key=True, default=key, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    image = models.ForeignKey(FoodImage, on_delete=models.CASCADE)
    status = models.CharField(max_length=20, default='unavailable')
    model_version = models.CharField(max_length=100, blank=True)
    candidates = models.JSONField(default=list)
    error_code = models.CharField(max_length=60, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class Meal(models.Model):
    id = models.UUIDField(primary_key=True, default=key, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='meals')
    eaten_at = models.DateTimeField()
    meal_type = models.CharField(max_length=20)
    notes = models.TextField(blank=True)
    image = models.ForeignKey(FoodImage, null=True, blank=True, on_delete=models.SET_NULL)
    version = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=['user', 'eaten_at'])]
        ordering = ['-eaten_at']


class MealItem(models.Model):
    id = models.UUIDField(primary_key=True, default=key, editable=False)
    meal = models.ForeignKey(Meal, on_delete=models.CASCADE, related_name='items')
    food = models.ForeignKey(Food, null=True, on_delete=models.SET_NULL)
    food_name = models.CharField(max_length=120)
    grams = models.DecimalField(max_digits=8, decimal_places=2, validators=[MinValueValidator(0)])
    kcal = models.DecimalField(max_digits=9, decimal_places=2)
    protein_g = models.DecimalField(max_digits=9, decimal_places=2)
    carbs_g = models.DecimalField(max_digits=9, decimal_places=2)
    fat_g = models.DecimalField(max_digits=9, decimal_places=2)


class IdempotencyRecord(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    operation_id = models.UUIDField()
    meal = models.ForeignKey(Meal, on_delete=models.CASCADE)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['user', 'operation_id'], name='unique_meal_operation')]
