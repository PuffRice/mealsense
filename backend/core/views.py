from datetime import timedelta
from decimal import Decimal
from uuid import uuid4
from zoneinfo import ZoneInfo
from hashlib import sha256

from PIL import Image, UnidentifiedImageError
from django.conf import settings
from django.contrib.auth import authenticate, login, logout, password_validation
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.http import FileResponse, Http404, JsonResponse
from django.middleware.csrf import get_token
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import (Food, FoodImage, FoodPrediction, Meal, NutritionGoal,
                     NutritionRecord, NutritionSource, Profile, RecognitionResult, User)
from .serializers import FoodSerializer, MealInputSerializer, MealSerializer, ProfileSerializer
from .services import (GOAL_FIELDS, create_meal, date_window, delete_private_image,
                       delete_user_with_media, goal_values_for_user,
                       matched_catalog_foods, owned_image, provider_image_bytes,
                       recognize_with_provider, replace_meal_items, revise_profile_goal)


@ensure_csrf_cookie
def csrf_token(request):
    return JsonResponse({'csrfToken': get_token(request)})


@method_decorator(csrf_protect, name='dispatch')
class RegisterView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        email = str(request.data.get('email', '')).strip().lower()
        password = str(request.data.get('password', ''))
        name = str(request.data.get('display_name', '')).strip()[:80]
        timezone_name = str(request.data.get('timezone', 'Asia/Dhaka'))
        gender = str(request.data.get('gender', '')).strip().lower()
        dob_raw = request.data.get('date_of_birth') or None
        if dob_raw == '':
            dob_raw = None
        if not email or '@' not in email:
            raise ValidationError({'email': 'Enter a valid email.'})
        try:
            password_validation.validate_password(password)
        except Exception as exc:
            raise ValidationError({'password': list(exc.messages)}) from None
        try:
            ZoneInfo(timezone_name)
        except Exception:
            raise ValidationError({'timezone': 'Unknown timezone.'}) from None
        profile_serializer = ProfileSerializer(
            data={'timezone': timezone_name, 'gender': gender, 'date_of_birth': dob_raw},
            partial=True,
        )
        profile_serializer.is_valid(raise_exception=True)
        try:
            with transaction.atomic():
                user = User.objects.create_user(email=email, password=password, display_name=name)
                Profile.objects.create(
                    user=user,
                    timezone=timezone_name,
                    gender=profile_serializer.validated_data.get('gender', ''),
                    date_of_birth=profile_serializer.validated_data.get('date_of_birth'),
                )
        except IntegrityError:
            raise ValidationError({'email': 'Account already exists.'}) from None
        login(request, user)
        return Response(user_payload(user), status=status.HTTP_201_CREATED)


@method_decorator(csrf_protect, name='dispatch')
class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        user = authenticate(request, email=str(request.data.get('email', '')).strip().lower(),
                            password=request.data.get('password', ''))
        if user is None:
            return Response({'error': 'Invalid email or password.'}, status=400)
        login(request, user)
        Profile.objects.get_or_create(user=user)
        return Response(user_payload(user))


class LogoutView(APIView):
    def post(self, request):
        logout(request)
        return Response(status=204)


def user_payload(user):
    profile, _ = Profile.objects.get_or_create(user=user)
    profile_data = ProfileSerializer(profile).data
    goal_values = goal_values_for_user(user)
    if goal_values is not None:
        profile_data.update(goal_values)
    return {'id': str(user.id), 'email': user.email, 'display_name': user.display_name,
            'profile': profile_data}


class MeView(APIView):
    def get(self, request):
        return Response(user_payload(request.user))

    def patch(self, request):
        profile, _ = Profile.objects.get_or_create(user=request.user)
        raw_profile = dict(request.data.get('profile', {}) or {})
        for nullable_key in ('date_of_birth', 'height_cm', 'weight_kg'):
            if raw_profile.get(nullable_key) == '':
                raw_profile[nullable_key] = None
        serializer = ProfileSerializer(profile, data=raw_profile, partial=True)
        serializer.is_valid(raise_exception=True)
        try:
            ZoneInfo(serializer.validated_data.get('timezone', profile.timezone))
        except Exception:
            raise ValidationError({'timezone': 'Unknown timezone.'}) from None
        with transaction.atomic():
            serializer.save()
            if any(field in raw_profile for field in GOAL_FIELDS):
                revise_profile_goal(profile)
            if 'display_name' in request.data:
                request.user.display_name = str(request.data['display_name']).strip()[:80]
                request.user.save(update_fields=['display_name'])
        return Response(user_payload(request.user))

    def delete(self, request):
        user = request.user
        if not user.check_password(str(request.data.get('password', ''))):
            raise ValidationError({'password': 'Enter your current password to delete your account.'})
        delete_user_with_media(user)
        logout(request)
        return Response(status=204)


class FoodListView(APIView):
    def get(self, request):
        query = str(request.query_params.get('q', '')).strip()[:80]
        foods = Food.objects.filter(Q(created_by=request.user) | Q(created_by__isnull=True), is_active=True)
        foods = foods.select_related('current_nutrition__active_record__source').prefetch_related('servings')
        if query:
            foods = foods.filter(Q(name__icontains=query) | Q(name_bn__icontains=query) |
                                 Q(aliases__alias__icontains=query)).distinct()
        return Response(FoodSerializer(foods[:100], many=True).data)

    def post(self, request):
        data = request.data.copy()
        data['source'] = 'User supplied'
        data['source_ref'] = ''
        serializer = FoodSerializer(data=data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            food = serializer.save(created_by=request.user)
            source, _ = NutritionSource.objects.get_or_create(name='User supplied')
            NutritionRecord.objects.create(
                food=food, source=source, version=1, verification_status='user_supplied',
                nutrient_values={
                    'kcal': str(food.kcal_100g), 'protein_g': str(food.protein_100g),
                    'carbs_g': str(food.carbs_100g), 'fat_g': str(food.fat_100g),
                })
        return Response(FoodSerializer(food).data, status=201)


def user_image(user, image_id):
    return owned_image(user, image_id)


class MealListView(APIView):
    def get(self, request):
        meals = Meal.objects.filter(user=request.user).prefetch_related('items')
        date_text = request.query_params.get('date')
        if date_text:
            profile, _ = Profile.objects.get_or_create(user=request.user)
            start, end = date_window(date_text, profile.timezone)
            meals = meals.filter(eaten_at__gte=start, eaten_at__lt=end)
        return Response(MealSerializer(meals[:100], many=True).data)

    def post(self, request):
        serializer = MealInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        _, created, response_snapshot = create_meal(request.user, serializer.validated_data)
        return Response(response_snapshot, status=201 if created else 200)


class MealDetailView(APIView):
    def get_object(self, request, pk):
        try:
            return Meal.objects.prefetch_related('items').get(pk=pk, user=request.user)
        except Meal.DoesNotExist:
            raise Http404

    def get(self, request, pk):
        return Response(MealSerializer(self.get_object(request, pk)).data)

    def patch(self, request, pk):
        serializer = MealInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        with transaction.atomic():
            try:
                meal = Meal.objects.select_for_update().get(pk=pk, user=request.user)
            except Meal.DoesNotExist:
                raise Http404 from None
            if data.get('version') != meal.version:
                return Response({'error': 'Meal changed on another device.', 'current': MealSerializer(meal).data}, status=409)
            meal.eaten_at, meal.meal_type = data['eaten_at'], data['meal_type']
            meal.notes = data.get('notes', '')
            meal.image = user_image(request.user, data.get('image_id'))
            meal.version += 1
            meal.save()
            replace_meal_items(meal, data['items'])
        return Response(MealSerializer(meal).data)

    def delete(self, request, pk):
        meal = self.get_object(request, pk)
        image = meal.image
        meal.delete()
        if image and not Meal.objects.filter(image=image).exists():
            delete_private_image(request.user, image.id)
        return Response(status=204)


def totals(meals):
    values = {'kcal': Decimal('0'), 'protein_g': Decimal('0'), 'carbs_g': Decimal('0'), 'fat_g': Decimal('0')}
    for meal in meals:
        for item in meal.items.all():
            for name in values:
                values[name] += getattr(item, name)
    return {key: str(value) for key, value in values.items()}


class DailyView(APIView):
    def get(self, request):
        profile, _ = Profile.objects.get_or_create(user=request.user)
        date = request.query_params.get('date') or timezone.localtime(timezone.now(), ZoneInfo(profile.timezone)).date().isoformat()
        start, end = date_window(date, profile.timezone)
        meals = Meal.objects.filter(user=request.user, eaten_at__gte=start, eaten_at__lt=end).prefetch_related('items')
        daily_totals = totals(meals)
        goal = (NutritionGoal.objects.filter(user=request.user, effective_from__lte=date)
                .filter(Q(effective_until__isnull=True) | Q(effective_until__gt=date))
                .prefetch_related('targets').order_by('-version').first())
        progress = []
        if goal:
            for target in goal.targets.all():
                actual = Decimal(daily_totals.get(target.nutrient_name, '0'))
                progress.append({'nutrient': target.nutrient_name, 'actual': str(actual),
                                 'target': str(target.target_value), 'unit': target.unit,
                                 'goal_version': goal.version})
        return Response({'date': date, 'totals': daily_totals, 'meal_count': meals.count(), 'progress': progress})


class NutritionGoalsView(APIView):
    def get(self, request):
        goals = NutritionGoal.objects.filter(user=request.user).prefetch_related('targets').order_by('-version')[:50]
        return Response([{'id': goal.id, 'version': goal.version, 'effective_from': goal.effective_from,
                          'effective_until': goal.effective_until, 'status': goal.status,
                          'targets': [{'nutrient': target.nutrient_name, 'value': str(target.target_value),
                                       'unit': target.unit, 'type': target.target_type} for target in goal.targets.all()]}
                         for goal in goals])


class WeeklyView(APIView):
    def get(self, request):
        profile, _ = Profile.objects.get_or_create(user=request.user)
        today = timezone.localtime(timezone.now(), ZoneInfo(profile.timezone)).date()
        start_date = today - timedelta(days=6)
        days = []
        for offset in range(7):
            date = (start_date + timedelta(days=offset)).isoformat()
            start, end = date_window(date, profile.timezone)
            meals = Meal.objects.filter(user=request.user, eaten_at__gte=start, eaten_at__lt=end).prefetch_related('items')
            days.append({'date': date, 'totals': totals(meals), 'meal_count': meals.count()})
        return Response(days)


class RecognitionView(APIView):
    def post(self, request):
        upload = request.FILES.get('image')
        if not upload:
            raise ValidationError({'image': 'Choose an image.'})
        if upload.size > 8 * 1024 * 1024:
            return Response({'image': 'Image exceeds 8 MB.'}, status=413)
        try:
            Image.MAX_IMAGE_PIXELS = 20_000_000
            image = Image.open(upload)
            image.verify()
            upload.seek(0)
            image = Image.open(upload)
            if image.format not in ('JPEG', 'PNG', 'WEBP') or image.width * image.height > 20_000_000:
                raise ValueError()
            mime = Image.MIME[image.format]
            extension = {'JPEG': 'jpg', 'PNG': 'png', 'WEBP': 'webp'}[image.format]
            upload.seek(0)
        except (UnidentifiedImageError, ValueError, OSError, Image.DecompressionBombError):
            raise ValidationError({'image': 'Use a valid JPEG, PNG, or WebP under 20 megapixels.'}) from None
        upload.name = f'{uuid4().hex}.{extension}'
        checksum = sha256(upload.read()).hexdigest()
        upload.seek(0)
        if settings.AI_PROVIDER == 'local':
            # Preserve the source pixels and EXIF for checkpoint preprocessing.
            provider_bytes, provider_mime = upload.read(), mime
        else:
            provider_bytes, provider_mime = provider_image_bytes(image)
        upload.seek(0)
        stored = FoodImage.objects.create(user=request.user, file=upload, mime_type=mime,
                                         size_bytes=upload.size, width=image.width,
                                         height=image.height, checksum=checksum)
        result = recognize_with_provider(provider_bytes, provider_mime)
        food_ids = matched_catalog_foods(result['candidates'], request.user)
        with transaction.atomic():
            prediction = FoodPrediction.objects.create(user=request.user, image=stored, status=result['status'],
                                                       model_version=result['model_version'],
                                                       candidates=[], error_code=result['error_code'],
                                                       completed_at=timezone.now())
            candidates = []
            for rank, item in enumerate(result['candidates'], start=1):
                food_id = food_ids.get(item['name'])
                saved_result = RecognitionResult.objects.create(
                    session=prediction, food_id=food_id, original_label=item['name'],
                    normalized_label=item['name'].casefold().strip(), rank=rank,
                    confidence=Decimal(str(item['confidence'])))
                candidates.append(dict(item, food_id=food_id, result_id=str(saved_result.id)))
            prediction.candidates = candidates
            prediction.save(update_fields=['candidates'])
        messages = {
            'completed': 'These are suggestions only. Confirm the food and serving size before saving.',
            'failed': 'Recognition failed. Add food manually.',
        }
        return Response({'id': str(prediction.id), 'image_id': str(stored.id), 'status': prediction.status,
                         'candidates': prediction.candidates, 'model_version': prediction.model_version,
                         'error_code': prediction.error_code,
                         'message': messages.get(prediction.status, 'Recognition is not configured yet. Add food manually.')},
                        status=201)


class RecognitionDetailView(APIView):
    def get(self, request, pk):
        try:
            prediction = FoodPrediction.objects.get(pk=pk, user=request.user)
        except FoodPrediction.DoesNotExist:
            raise Http404
        return Response({'id': str(prediction.id), 'image_id': str(prediction.image_id),
                         'status': prediction.status, 'candidates': prediction.candidates,
                         'model_version': prediction.model_version, 'error_code': prediction.error_code})


class PrivateImageView(APIView):
    def get(self, request, pk):
        try:
            image = FoodImage.objects.get(pk=pk, user=request.user)
        except FoodImage.DoesNotExist:
            raise Http404
        response = FileResponse(image.file.open('rb'), content_type=image.mime_type)
        response['Cache-Control'] = 'private, no-store'
        return response

    def delete(self, request, pk):
        if not delete_private_image(request.user, pk):
            raise Http404
        return Response(status=204)
