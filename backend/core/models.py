import re
import secrets
import uuid
from decimal import Decimal, InvalidOperation
from django.contrib.auth.base_user import BaseUserManager
from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, RegexValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone


def key():
    return uuid.uuid4()


def doctor_access_token():
    return secrets.token_urlsafe(32)


def validate_phone_number(value):
    """Accept common phone punctuation; storage stays normalized digits."""
    digits = re.sub(r'\D', '', str(value))
    if not 6 <= len(digits) <= 15:
        raise ValidationError('Phone must be 6-15 digits including country code.')


MAX_PROFILE_PICTURE_SIZE = 5 * 1024 * 1024
USERNAME_VALIDATOR = RegexValidator(
    regex=r'^[a-z0-9](?:[a-z0-9._-]{1,28}[a-z0-9])?$',
    message='Username must be 3-30 characters and use letters, numbers, dots, underscores, or hyphens.',
)


def validate_profile_picture_size(value):
    from django.core.exceptions import ValidationError
    if value.size > MAX_PROFILE_PICTURE_SIZE:
        raise ValidationError('Profile picture must be 5 MB or smaller.')


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
    username = models.CharField(
        max_length=30,
        unique=True,
        default='',
        validators=[USERNAME_VALIDATOR],
    )
    email = models.EmailField(unique=True)
    display_name = models.CharField(max_length=80, blank=True)
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []
    objects = UserManager()

    def save(self, *args, **kwargs):
        if not self.username:
            base = ''.join(char for char in self.email.split('@', 1)[0].lower() if char.isalnum())[:24] or 'user'
            candidate = base
            suffix = 1
            while type(self).objects.filter(username=candidate).exclude(pk=self.pk).exists():
                candidate = f'{base[:24 - len(str(suffix))]}{suffix}'
                suffix += 1
            self.username = candidate
        else:
            self.username = self.username.strip().lower()
        return super().save(*args, **kwargs)


class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    profile_picture = models.ImageField(
        upload_to='profile_pictures/%Y/%m/%d',
        blank=True,
        null=True,
        validators=[validate_profile_picture_size],
    )
    timezone = models.CharField(max_length=64, default='Asia/Dhaka')
    units = models.CharField(max_length=12, default='metric')
    # Normalized digits with country code (no '+'), e.g. 8801712345678.
    # NULL when unset so the unique constraint allows multiple missing values.
    phone = models.CharField(
        max_length=24,
        blank=True,
        default=None,
        null=True,
        unique=True,
        validators=[validate_phone_number],
    )
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
    name_bn = models.CharField(max_length=120, blank=True)
    category = models.CharField(max_length=60, blank=True)
    is_active = models.BooleanField(default=True)
    is_verified = models.BooleanField(default=False)
    kcal_100g = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True,
                                    validators=[MinValueValidator(0)])
    protein_100g = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True,
                                       validators=[MinValueValidator(0)])
    carbs_100g = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True,
                                     validators=[MinValueValidator(0)])
    fat_100g = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True,
                                   validators=[MinValueValidator(0)])
    source = models.CharField(max_length=160)
    source_ref = models.CharField(max_length=250, blank=True)
    is_sample = models.BooleanField(default=False)

    class Meta:
        ordering = ['name']


class FoodAlias(models.Model):
    food = models.ForeignKey(Food, on_delete=models.CASCADE, related_name='aliases')
    alias = models.CharField(max_length=120)
    language = models.CharField(max_length=16, blank=True)
    region = models.CharField(max_length=80, blank=True)
    is_verified = models.BooleanField(default=False)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['food', 'alias', 'language', 'region'], name='unique_food_alias')]


class FoodServing(models.Model):
    food = models.ForeignKey(Food, on_delete=models.CASCADE, related_name='servings')
    name = models.CharField(max_length=100)
    name_bn = models.CharField(max_length=100, blank=True)
    definition = models.TextField(blank=True)
    weight_g = models.DecimalField(max_digits=8, decimal_places=2, validators=[MinValueValidator(0)])
    preparation_state = models.CharField(max_length=80, blank=True)
    is_approximate = models.BooleanField(default=True)
    is_default = models.BooleanField(default=False)

    class Meta:
        constraints = [models.CheckConstraint(condition=Q(weight_g__gt=0), name='serving_positive_weight')]


class NutritionSource(models.Model):
    name = models.CharField(max_length=160)
    reference = models.CharField(max_length=250, blank=True)
    license = models.CharField(max_length=160, blank=True)
    retrieved_at = models.DateTimeField(null=True, blank=True)
    is_trusted = models.BooleanField(default=False)


class NutritionRecord(models.Model):
    food = models.ForeignKey(Food, on_delete=models.PROTECT, related_name='nutrition_records')
    source = models.ForeignKey(NutritionSource, on_delete=models.PROTECT)
    version = models.PositiveIntegerField()
    basis_quantity = models.DecimalField(max_digits=8, decimal_places=2, default=100)
    basis_unit = models.CharField(max_length=16, default='g edible')
    nutrient_values = models.JSONField(default=dict)
    verification_status = models.CharField(max_length=20, default='unverified')
    calculation_method = models.CharField(max_length=160, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['food', 'version'], name='unique_food_nutrition_version'),
            models.CheckConstraint(condition=Q(basis_quantity__gt=0), name='nutrition_positive_basis'),
        ]

    def save(self, *args, **kwargs):
        if self.pk and FoodNutrition.objects.filter(active_record_id=self.pk).exists():
            from django.core.exceptions import ValidationError
            previous = type(self).objects.get(pk=self.pk)
            protected = ('food_id', 'source_id', 'version', 'basis_quantity', 'basis_unit',
                         'nutrient_values', 'verification_status', 'calculation_method')
            if any(getattr(previous, field) != getattr(self, field) for field in protected):
                raise ValidationError('An active nutrition record is immutable; create a new version.')
        return super().save(*args, **kwargs)


class FoodNutrition(models.Model):
    food = models.OneToOneField(Food, on_delete=models.CASCADE, related_name='current_nutrition')
    active_record = models.ForeignKey(NutritionRecord, on_delete=models.PROTECT)
    updated_at = models.DateTimeField(auto_now=True)

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.active_record_id and self.food_id and self.active_record.food_id != self.food_id:
            raise ValidationError('Active nutrition record belongs to another food.')
        if self.active_record_id and self.active_record.verification_status != 'approved':
            raise ValidationError('Only an approved nutrition record may be active.')
        if self.active_record_id:
            record = self.active_record
            if record.basis_unit != 'g edible':
                raise ValidationError('The active record must use an edible-gram basis.')
            for name in ('kcal', 'protein_g', 'carbs_g', 'fat_g'):
                try:
                    value = Decimal(str(record.nutrient_values[name]))
                except (KeyError, TypeError, InvalidOperation):
                    raise ValidationError(f'Active record is missing valid {name}.') from None
                if not value.is_finite() or value < 0:
                    raise ValidationError(f'Active record has invalid {name}.')

    def save(self, *args, **kwargs):
        self.clean()
        return super().save(*args, **kwargs)


class FoodImage(models.Model):
    id = models.UUIDField(primary_key=True, default=key, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    file = models.ImageField(upload_to='meal_images/%Y/%m/%d')
    mime_type = models.CharField(max_length=40)
    size_bytes = models.PositiveIntegerField()
    width = models.PositiveIntegerField(default=0)
    height = models.PositiveIntegerField(default=0)
    checksum = models.CharField(max_length=64, blank=True)
    deletion_requested_at = models.DateTimeField(null=True, blank=True)
    deletion_failed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class PrivateMealImage(FoodImage):
    class Meta:
        proxy = True


class MediaDeletionJob(models.Model):
    storage_key = models.CharField(max_length=500, unique=True)
    requested_at = models.DateTimeField(default=timezone.now)
    completed_at = models.DateTimeField(null=True, blank=True)
    attempts = models.PositiveIntegerField(default=0)
    last_error_code = models.CharField(max_length=40, blank=True)


class FoodPrediction(models.Model):
    id = models.UUIDField(primary_key=True, default=key, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    image = models.ForeignKey(FoodImage, on_delete=models.CASCADE)
    status = models.CharField(max_length=20, default='unavailable')
    model_version = models.CharField(max_length=100, blank=True)
    candidates = models.JSONField(default=list)
    error_code = models.CharField(max_length=60, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)


class RecognitionSession(FoodPrediction):
    class Meta:
        proxy = True


class FoodDetection(models.Model):
    session = models.ForeignKey(FoodPrediction, on_delete=models.CASCADE, related_name='detections')
    food = models.ForeignKey(Food, null=True, blank=True, on_delete=models.SET_NULL)
    bounding_box = models.JSONField(null=True, blank=True)
    confidence = models.DecimalField(max_digits=4, decimal_places=3, null=True, blank=True)
    detection_index = models.PositiveIntegerField()

    class Meta:
        constraints = [models.UniqueConstraint(fields=['session', 'detection_index'], name='unique_detection_index')]


class RecognitionResult(models.Model):
    session = models.ForeignKey(FoodPrediction, on_delete=models.CASCADE, related_name='results')
    detection = models.ForeignKey(FoodDetection, null=True, blank=True, on_delete=models.SET_NULL)
    food = models.ForeignKey(Food, null=True, blank=True, on_delete=models.SET_NULL)
    original_label = models.CharField(max_length=120)
    normalized_label = models.CharField(max_length=120)
    rank = models.PositiveIntegerField()
    confidence = models.DecimalField(max_digits=4, decimal_places=3, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['session', 'rank'], condition=Q(detection__isnull=True), name='unique_whole_image_rank'),
            models.UniqueConstraint(fields=['detection', 'rank'], condition=Q(detection__isnull=False), name='unique_region_rank'),
        ]

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.detection_id and self.session_id and self.detection.session_id != self.session_id:
            raise ValidationError('Detection belongs to another recognition session.')

    def save(self, *args, **kwargs):
        self.clean()
        return super().save(*args, **kwargs)


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
    serving = models.ForeignKey(FoodServing, null=True, blank=True, on_delete=models.SET_NULL)
    recognition_result = models.ForeignKey(RecognitionResult, null=True, blank=True, on_delete=models.SET_NULL)
    nutrition_record = models.ForeignKey(NutritionRecord, null=True, blank=True, on_delete=models.SET_NULL)
    food_name = models.CharField(max_length=120)
    grams = models.DecimalField(max_digits=8, decimal_places=2, validators=[MinValueValidator(0)])
    kcal = models.DecimalField(max_digits=9, decimal_places=2)
    protein_g = models.DecimalField(max_digits=9, decimal_places=2)
    carbs_g = models.DecimalField(max_digits=9, decimal_places=2)
    fat_g = models.DecimalField(max_digits=9, decimal_places=2)
    nutrition_source_snapshot = models.CharField(max_length=160, blank=True)
    nutrition_basis_snapshot = models.CharField(max_length=80, default='per 100 g edible')
    calculation_version = models.CharField(max_length=30, default='legacy-1')


class IdempotencyRecord(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    operation_id = models.UUIDField()
    request_hash = models.CharField(max_length=64, blank=True)
    meal = models.ForeignKey(Meal, null=True, blank=True, on_delete=models.SET_NULL)
    response_snapshot = models.JSONField(default=dict)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['user', 'operation_id'], name='unique_meal_operation')]


class NutritionGoal(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='nutrition_goals')
    version = models.PositiveIntegerField(default=1)
    effective_from = models.DateField()
    effective_until = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=12, default='active')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['user'], condition=Q(status='active'), name='one_active_nutrition_goal'),
            models.UniqueConstraint(fields=['user', 'version'], name='unique_user_goal_version'),
            models.CheckConstraint(condition=Q(effective_until__isnull=True) | Q(effective_until__gte=models.F('effective_from')),
                                   name='goal_valid_date_range'),
        ]


class NutrientTarget(models.Model):
    goal = models.ForeignKey(NutritionGoal, on_delete=models.CASCADE, related_name='targets')
    nutrient_name = models.CharField(max_length=30)
    target_value = models.DecimalField(max_digits=10, decimal_places=2)
    unit = models.CharField(max_length=16)
    target_type = models.CharField(max_length=12, default='exact')

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['goal', 'nutrient_name'], name='unique_goal_nutrient'),
            models.CheckConstraint(condition=Q(target_value__gte=0), name='target_nonnegative'),
        ]


class GoalProgress(models.Model):
    goal = models.ForeignKey(NutritionGoal, on_delete=models.CASCADE)
    target = models.ForeignKey(NutrientTarget, on_delete=models.CASCADE)
    progress_date = models.DateField()
    actual_value = models.DecimalField(max_digits=10, decimal_places=2)
    target_value = models.DecimalField(max_digits=10, decimal_places=2)
    goal_version_snapshot = models.PositiveIntegerField()
    calculated_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['target', 'progress_date'], name='unique_target_progress_day')]


class DoctorAccessRequest(models.Model):
    """Consent record for a doctor (no account) to view a patient's history.

    The doctor identifies the patient by email or phone from the public page.
    The patient approves or denies the request in their own app. On approval
    the request's view token becomes usable for a bounded window and the
    patient can revoke it at any time.
    """
    STATUS_PENDING = 'pending'
    STATUS_APPROVED = 'approved'
    STATUS_DENIED = 'denied'
    STATUS_REVOKED = 'revoked'
    STATUS_CHOICES = (
        (STATUS_PENDING, 'Pending'),
        (STATUS_APPROVED, 'Approved'),
        (STATUS_DENIED, 'Denied'),
        (STATUS_REVOKED, 'Revoked'),
    )

    id = models.UUIDField(primary_key=True, default=key, editable=False)
    patient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='doctor_access_requests')
    doctor_name = models.CharField(max_length=120)
    identifier_type = models.CharField(max_length=10)
    identifier = models.CharField(max_length=254)
    status = models.CharField(max_length=12, default=STATUS_PENDING, choices=STATUS_CHOICES)
    view_token = models.CharField(max_length=64, unique=True, default=doctor_access_token, editable=False)
    approved_at = models.DateTimeField(null=True, blank=True)
    denied_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['patient', '-created_at']),
            models.Index(fields=['patient', 'status']),
        ]
        constraints = [
            models.CheckConstraint(condition=Q(identifier_type__in=('email', 'phone')),
                                   name='doctor_request_identifier_type'),
            models.CheckConstraint(condition=Q(status__in=('pending', 'approved', 'denied', 'revoked')),
                                   name='doctor_request_status'),
        ]

    def is_active(self):
        return self.status == self.STATUS_APPROVED and self.expires_at is not None \
            and self.expires_at > timezone.now()

    def effective_status(self):
        """Status as seen by the doctor: an approved-but-expired request reads as expired."""
        if self.status == self.STATUS_APPROVED and not self.is_active():
            return 'expired'
        return self.status
