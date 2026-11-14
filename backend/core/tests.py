import json
import tempfile
from datetime import timedelta
from decimal import Decimal
from io import BytesIO
from unittest.mock import patch
from uuid import uuid4
from PIL import Image
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.utils import timezone
from .models import (DailyNutritionSummary, DoctorAccessRequest, Food, FoodAlias, FoodImage,
                     FoodLog, FoodNutrition, FoodPrediction, FoodServing, Meal, MediaDeletionJob,
                     NutritionGoal, NutritionRecord, NutritionSource,
                     RecognitionResult, Profile, User)
from .services import (DOCTOR_ACCESS_HOURS, DOCTOR_REQUEST_PENDING_MESSAGE, ProviderError,
                       matched_catalog_foods, normalize_candidates)


class MealApiTests(TestCase):
    def setUp(self):
        self.client = Client(enforce_csrf_checks=True)
        self.user = User.objects.create_user(email='a@example.com', password='secure-pass-123')
        Profile.objects.create(user=self.user)
        self.other = User.objects.create_user(email='b@example.com', password='secure-pass-123')
        Profile.objects.create(user=self.other)
        self.food = Food.objects.create(name='Test rice', category='Grain', kcal_100g=130,
            protein_100g=2.7, carbs_100g=28, fat_100g=0.3, source='Test fixture')
        self.client.get('/api/v1/auth/csrf/')
        self.csrf = self.client.cookies['csrftoken'].value
        response = self.post('/api/v1/auth/login/', {'email': self.user.email, 'password': 'secure-pass-123'})
        self.assertEqual(response.status_code, 200)
        self.client.get('/api/v1/auth/csrf/')
        self.csrf = self.client.cookies['csrftoken'].value

    def post(self, path, body):
        return self.client.post(path, data=json.dumps(body), content_type='application/json', HTTP_X_CSRFTOKEN=self.csrf)

    def payload(self, **extra):
        return {'eaten_at': timezone.now().isoformat(), 'meal_type': 'lunch',
                'items': [{'food_id': str(self.food.id), 'grams': 150}], **extra}

    def test_profile_picture_upload_is_private_and_limited_to_five_megabytes(self):
        image_bytes = BytesIO()
        Image.new('RGB', (2, 2), 'red').save(image_bytes, format='PNG')
        image = SimpleUploadedFile('profile.png', image_bytes.getvalue(), content_type='image/png')
        response = self.client.post(
            '/api/v1/users/me/profile-picture/',
            {'profile_picture': image},
            HTTP_X_CSRFTOKEN=self.csrf,
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(response.json()['profile']['profile_picture_url'])
        self.assertEqual(
            self.client.get('/api/v1/users/me/profile-picture/').status_code,
            200,
        )

        oversized = SimpleUploadedFile(
            'oversized.png',
            b'0' * (5 * 1024 * 1024 + 1),
            content_type='image/png',
        )
        rejected = self.client.post(
            '/api/v1/users/me/profile-picture/',
            {'profile_picture': oversized},
            HTTP_X_CSRFTOKEN=self.csrf,
        )
        self.assertEqual(rejected.status_code, 400)

    def test_server_calculates_snapshot_totals_and_idempotent_retry(self):
        operation_id = str(uuid4())
        payload = self.payload(operation_id=operation_id, totals={'kcal': 99999})
        first = self.post('/api/v1/meals/', payload)
        self.assertEqual(first.status_code, 201, first.content)
        self.assertEqual(Decimal(first.json()['totals']['kcal']), Decimal('195.00'))
        second = self.post('/api/v1/meals/', payload)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(Meal.objects.count(), 1)
        self.food.kcal_100g = 999
        self.food.save()
        self.assertEqual(Decimal(self.client.get('/api/v1/meals/').json()[0]['totals']['kcal']), Decimal('195.00'))

    def test_reused_operation_id_with_changed_payload_is_conflict(self):
        operation_id = str(uuid4())
        self.assertEqual(self.post('/api/v1/meals/', self.payload(operation_id=operation_id)).status_code, 201)
        changed = self.post('/api/v1/meals/', self.payload(operation_id=operation_id,
            items=[{'food_id': str(self.food.id), 'grams': 300}]))
        self.assertEqual(changed.status_code, 409)
        self.assertEqual(Meal.objects.count(), 1)

    def test_retry_returns_original_response_after_meal_deletion(self):
        payload = self.payload(operation_id=str(uuid4()))
        first = self.post('/api/v1/meals/', payload)
        self.assertEqual(first.status_code, 201, first.content)
        self.assertEqual(self.client.delete(f"/api/v1/meals/{first.json()['id']}/",
                                            HTTP_X_CSRFTOKEN=self.csrf).status_code, 204)
        retry = self.post('/api/v1/meals/', payload)
        self.assertEqual(retry.status_code, 200, retry.content)
        self.assertEqual(retry.json(), first.json())
        self.assertEqual(Meal.objects.count(), 0)

    def test_custom_food_creates_versioned_source_and_meal_snapshot(self):
        response = self.post('/api/v1/foods/', {'name': 'Home dal', 'category': 'My foods',
            'kcal_100g': '120', 'protein_100g': '7', 'carbs_100g': '16', 'fat_100g': '3'})
        self.assertEqual(response.status_code, 201, response.content)
        food = Food.objects.get(pk=response.json()['id'])
        record = NutritionRecord.objects.get(food=food)
        self.assertEqual(record.verification_status, 'user_supplied')
        meal = self.post('/api/v1/meals/', self.payload(items=[{'food_id': str(food.id), 'grams': 200}]))
        self.assertEqual(meal.status_code, 201, meal.content)
        item = meal.json()['items'][0]
        self.assertEqual(Decimal(item['kcal']), Decimal('240.00'))
        self.assertEqual(item['nutrition_source_snapshot'], 'User supplied')
        self.assertEqual(item['calculation_version'], 'v3-1')

    def test_food_specific_serving_and_bengali_alias(self):
        FoodAlias.objects.create(food=self.food, alias='bhaat', language='bn')
        serving = FoodServing.objects.create(food=self.food, name='small bowl',
            definition='Cooked rice in a 200 ml bowl', weight_g=150, preparation_state='cooked')
        foods = self.client.get('/api/v1/foods/?q=bhaat').json()
        self.assertEqual(len(foods), 1)
        self.assertEqual(foods[0]['servings'][0]['weight_g'], '150.00')
        meal = self.post('/api/v1/meals/', self.payload(items=[
            {'food_id': str(self.food.id), 'grams': 150, 'serving_id': serving.id}]))
        self.assertEqual(meal.status_code, 201, meal.content)
        self.assertEqual(meal.json()['items'][0]['serving'], serving.id)
        other_food = Food.objects.create(name='Other food', kcal_100g=1, protein_100g=1,
            carbs_100g=1, fat_100g=1, source='Test fixture')
        mismatch = self.post('/api/v1/meals/', self.payload(items=[
            {'food_id': str(other_food.id), 'grams': 150, 'serving_id': serving.id}]))
        self.assertEqual(mismatch.status_code, 400)

    def test_model_catalog_foods_are_shared_with_unknown_nutrition(self):
        foods = self.client.get('/api/v1/foods/?q=biriyani').json()
        self.assertEqual(len(foods), 1)
        self.assertEqual(foods[0]['name'], 'Biryani')
        self.assertEqual(foods[0]['name_bn'], 'বিরিয়ানি')
        self.assertIsNone(foods[0]['kcal_100g'])
        self.assertIsNone(foods[0]['protein_100g'])
        self.assertFalse(foods[0]['is_verified'])

    def test_model_catalog_food_cannot_create_fake_nutrition_snapshot(self):
        food = Food.objects.get(created_by=None, name='Biryani')
        response = self.post('/api/v1/meals/', self.payload(items=[
            {'food_id': str(food.id), 'grams': 100},
        ]))
        self.assertEqual(response.status_code, 400)
        self.assertIn('missing a required nutrient value', str(response.json()))
        self.assertFalse(Meal.objects.filter(user=self.user, items__food=food).exists())

    def test_unapproved_nutrition_revision_does_not_change_logged_amount(self):
        source = NutritionSource.objects.create(name='New import')
        NutritionRecord.objects.create(food=self.food, source=source, version=2,
            verification_status='unverified', nutrient_values={
                'kcal': '999', 'protein_g': '1', 'carbs_g': '1', 'fat_g': '1'})
        meal = self.post('/api/v1/meals/', self.payload())
        self.assertEqual(meal.status_code, 201, meal.content)
        self.assertEqual(Decimal(meal.json()['items'][0]['kcal']), Decimal('195.00'))

    def test_goal_revision_is_dated_and_progress_uses_target(self):
        first = self.client.patch('/api/v1/users/me/',
            data=json.dumps({'profile': {'daily_kcal_goal': 2000, 'protein_goal_g': 80}}),
            content_type='application/json', HTTP_X_CSRFTOKEN=self.csrf)
        self.assertEqual(first.status_code, 200, first.content)
        second = self.client.patch('/api/v1/users/me/',
            data=json.dumps({'profile': {'daily_kcal_goal': 2200}}),
            content_type='application/json', HTTP_X_CSRFTOKEN=self.csrf)
        self.assertEqual(second.status_code, 200, second.content)
        self.assertEqual(NutritionGoal.objects.filter(user=self.user).count(), 2)
        self.assertEqual(second.json()['profile']['daily_kcal_goal'], 2200)
        goals = self.client.get('/api/v1/nutrition/goals/').json()
        self.assertEqual(goals[0]['version'], 2)
        self.assertEqual(goals[0]['targets'][0]['nutrient'], 'kcal')
        day = self.client.get('/api/v1/nutrition/daily/').json()
        self.assertEqual(day['progress'][0]['target'], '2200.00')

    def test_active_nutrition_must_match_food_and_be_approved(self):
        source = NutritionSource.objects.create(name='Fixture')
        other_food = Food.objects.create(name='Other', kcal_100g=1, protein_100g=1,
            carbs_100g=1, fat_100g=1, source='Fixture')
        record = NutritionRecord.objects.create(food=other_food, source=source, version=1,
            verification_status='approved', nutrient_values={'kcal': '1'})
        with self.assertRaises(DjangoValidationError):
            FoodNutrition.objects.create(food=self.food, active_record=record)

    def test_active_nutrition_record_cannot_be_rewritten(self):
        source = NutritionSource.objects.create(name='Reviewed')
        record = NutritionRecord.objects.create(food=self.food, source=source, version=1,
            verification_status='approved', nutrient_values={
                'kcal': '130', 'protein_g': '2.7', 'carbs_g': '28', 'fat_g': '0.3'})
        FoodNutrition.objects.create(food=self.food, active_record=record)
        record.nutrient_values['kcal'] = '999'
        with self.assertRaises(DjangoValidationError):
            record.save()

    def test_owner_access_and_foreign_custom_food_blocked(self):
        meal_id = self.post('/api/v1/meals/', self.payload()).json()['id']
        private_food = Food.objects.create(name='Private food', kcal_100g=1, protein_100g=1,
            carbs_100g=1, fat_100g=1, source='User supplied', created_by=self.other)
        self.assertEqual(self.post('/api/v1/meals/', self.payload(items=[{'food_id': str(private_food.id), 'grams': 100}])).status_code, 400)
        self.client.logout()
        self.client.get('/api/v1/auth/csrf/')
        self.csrf = self.client.cookies['csrftoken'].value
        self.post('/api/v1/auth/login/', {'email': self.other.email, 'password': 'secure-pass-123'})
        self.client.get('/api/v1/auth/csrf/')
        self.csrf = self.client.cookies['csrftoken'].value
        self.assertEqual(self.client.get(f'/api/v1/meals/{meal_id}/').status_code, 404)
        self.assertEqual(self.client.delete(f'/api/v1/meals/{meal_id}/', HTTP_X_CSRFTOKEN=self.csrf).status_code, 404)

    def test_stale_edit_returns_conflict(self):
        meal = self.post('/api/v1/meals/', self.payload()).json()
        response = self.client.patch(f"/api/v1/meals/{meal['id']}/", data=json.dumps(self.payload(version=99)),
            content_type='application/json', HTTP_X_CSRFTOKEN=self.csrf)
        self.assertEqual(response.status_code, 409)

    def test_mutation_requires_csrf(self):
        response = self.client.post('/api/v1/meals/', data=json.dumps(self.payload()), content_type='application/json')
        self.assertEqual(response.status_code, 403)

    def test_account_deletion_requires_password(self):
        private = self.post('/api/v1/foods/', {'name': 'Private dal', 'kcal_100g': 120,
            'protein_100g': 7, 'carbs_100g': 16, 'fat_100g': 3})
        self.assertEqual(private.status_code, 201, private.content)
        self.assertTrue(NutritionRecord.objects.filter(food_id=private.json()['id']).exists())
        self.assertEqual(self.client.delete('/api/v1/users/me/', data=json.dumps({'password': 'wrong'}),
            content_type='application/json', HTTP_X_CSRFTOKEN=self.csrf).status_code, 400)
        self.assertTrue(User.objects.filter(pk=self.user.pk).exists())
        self.assertEqual(self.client.delete('/api/v1/users/me/', data=json.dumps({'password': 'secure-pass-123'}),
            content_type='application/json', HTTP_X_CSRFTOKEN=self.csrf).status_code, 204)
        self.assertFalse(User.objects.filter(pk=self.user.pk).exists())

    def test_image_upload_is_private_and_renamed(self):
        image = Image.new('RGB', (8, 8), 'green')
        buffer = BytesIO()
        image.save(buffer, format='PNG')
        upload = SimpleUploadedFile('private-family-photo.png', buffer.getvalue(), content_type='image/png')
        with tempfile.TemporaryDirectory() as folder, override_settings(MEDIA_ROOT=folder):
            response = self.client.post('/api/v1/recognitions/', data={'image': upload}, HTTP_X_CSRFTOKEN=self.csrf)
            self.assertEqual(response.status_code, 201, response.content)
            image_id = response.json()['image_id']
            self.assertNotIn('private-family-photo', FoodImage.objects.get(pk=image_id).file.name)
            img_res = self.client.get(f'/api/v1/images/{image_id}/')
            self.assertEqual(img_res.status_code, 200)
            img_res.close()
            self.client.logout()
            self.assertEqual(self.client.get(f'/api/v1/images/{image_id}/').status_code, 403)

    def test_image_delete_detaches_meal_and_removes_bytes(self):
        with tempfile.TemporaryDirectory() as folder, override_settings(MEDIA_ROOT=folder):
            upload = self.client.post('/api/v1/recognitions/', data={'image': png_upload()},
                                      HTTP_X_CSRFTOKEN=self.csrf)
            self.assertEqual(upload.status_code, 201, upload.content)
            image_id = upload.json()['image_id']
            file_name = FoodImage.objects.get(pk=image_id).file.name
            meal = self.post('/api/v1/meals/', self.payload(image_id=image_id))
            self.assertEqual(meal.status_code, 201, meal.content)
            with self.captureOnCommitCallbacks(execute=True):
                removed = self.client.delete(f'/api/v1/images/{image_id}/', HTTP_X_CSRFTOKEN=self.csrf)
            self.assertEqual(removed.status_code, 204)
            self.assertFalse(FoodImage.objects.filter(pk=image_id).exists())
            self.assertIsNone(Meal.objects.get(pk=meal.json()['id']).image_id)
            self.assertFalse(FoodImage._meta.get_field('file').storage.exists(file_name))
            self.assertIsNotNone(MediaDeletionJob.objects.get(storage_key=file_name).completed_at)

    def test_admin_models_registered_and_accessible(self):
        self.user.is_staff = True
        self.user.is_superuser = True
        self.user.save()
        self.client.force_login(self.user)
        res = self.client.get('/admin/', HTTP_HOST='localhost')
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, 'MealSense')
        self.assertContains(res, 'Foods')
        self.assertContains(res, 'Meals')

    def test_register_and_profile_update_with_gender_dob_bmi_fields(self):
        self.client.logout()
        self.client.get('/api/v1/auth/csrf/')
        self.csrf = self.client.cookies['csrftoken'].value
        reg_res = self.post('/api/v1/auth/register/', {
            'email': 'newuser@example.com',
            'password': 'secure-pass-123',
            'display_name': 'New User',
            'timezone': 'Asia/Dhaka',
            'gender': 'male',
            'date_of_birth': '2001-05-15',
        })
        self.assertEqual(reg_res.status_code, 201, reg_res.content)
        reg_data = reg_res.json()
        self.assertEqual(reg_data['profile']['gender'], 'male')
        self.assertEqual(reg_data['profile']['date_of_birth'], '2001-05-15')

        self.client.get('/api/v1/auth/csrf/')
        self.csrf = self.client.cookies['csrftoken'].value
        patch_res = self.client.patch(
            '/api/v1/users/me/',
            data=json.dumps({
                'display_name': 'Updated User',
                'profile': {
                    'gender': 'female',
                    'date_of_birth': '1999-11-20',
                    'height_cm': 168.5,
                    'weight_kg': 62.0,
                    'daily_kcal_goal': 2050,
                    'protein_goal_g': 100,
                    'carbs_goal_g': 240,
                    'fat_goal_g': 65,
                },
            }),
            content_type='application/json',
            HTTP_X_CSRFTOKEN=self.csrf,
        )
        self.assertEqual(patch_res.status_code, 200, patch_res.content)
        updated = patch_res.json()['profile']
        self.assertEqual(updated['gender'], 'female')
        self.assertEqual(updated['date_of_birth'], '1999-11-20')
        self.assertEqual(Decimal(updated['height_cm']), Decimal('168.5'))
        self.assertEqual(Decimal(updated['weight_kg']), Decimal('62.0'))

    def test_nutrition_preview_computes_server_side(self):
        response = self.post('/api/v1/nutrition/preview/', {
            'items': [{'key': 'rice-1', 'grams': 150, 'food_id': str(self.food.id)}],
        })
        self.assertEqual(response.status_code, 200, response.content)
        row = response.json()['items'][0]
        self.assertEqual(row['kcal'], '195.00')   # 130 * 150 / 100, Decimal
        self.assertEqual(row['protein_g'], '4.05')
        self.assertEqual(row['carbs_g'], '42.00')
        self.assertEqual(row['fat_g'], '0.45')
        self.assertEqual(response.json()['totals'], {
            'kcal': '195.00', 'protein_g': '4.05', 'carbs_g': '42.00', 'fat_g': '0.45'})
        self.assertFalse(response.json()['pending'])

    def test_nutrition_preview_accepts_inline_values(self):
        response = self.post('/api/v1/nutrition/preview/', {
            'items': [{'key': 'custom', 'grams': 200, 'kcal_100g': '180.5',
                       'protein_100g': '5', 'carbs_100g': '20', 'fat_100g': '3'}],
        })
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()['totals']['kcal'], '361.00')
        self.assertEqual(response.json()['totals']['protein_g'], '10.00')

    def test_nutrition_preview_unknown_nutrient_stays_null_not_zero(self):
        response = self.post('/api/v1/nutrition/preview/', {
            'items': [{'key': 'custom', 'grams': 200, 'protein_100g': '5'},
                      {'key': 'rice', 'grams': 100, 'food_id': str(self.food.id)}],
        })
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertTrue(body['pending'])
        self.assertIsNone(body['totals']['kcal'])  # one item lacks kcal -> total is unknown, not 0
        self.assertEqual(body['totals']['protein_g'], '12.70')  # 5 * 200/100 + 2.7 * 100/100
        self.assertIsNone(body['items'][0]['kcal'])

    def test_nutrition_preview_rejects_other_users_food(self):
        other_food = Food.objects.create(created_by=self.other, name='Secret dish', category='Curry',
                                         kcal_100g=999, protein_100g=1, carbs_100g=1, fat_100g=1,
                                         source='Private')
        response = self.post('/api/v1/nutrition/preview/', {
            'items': [{'key': 'x', 'grams': 100, 'food_id': str(other_food.id)}],
        })
        self.assertEqual(response.status_code, 400, response.content)

    def test_goal_suggestions_match_expected_values(self):
        response = self.post('/api/v1/goals/suggestions/', {
            'height_cm': 170, 'weight_kg': 65, 'gender': 'male',
        })
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()['suggestion']
        self.assertEqual(body['bmi'], '22.5')
        self.assertEqual(body['category'], 'Healthy weight')
        self.assertEqual(body['kcal'], 2190)
        self.assertEqual(body['protein_g'], 104)
        self.assertEqual(body['carbs_g'], 291)
        self.assertEqual(body['fat_g'], 68)
        self.assertEqual(body['healthy_min_kg'], '53.5')
        self.assertEqual(body['healthy_max_kg'], '72.0')

    def test_goal_suggestions_return_null_without_inputs(self):
        response = self.post('/api/v1/goals/suggestions/', {})
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()['suggestion'])

    def test_goal_suggestions_reject_out_of_range_height(self):
        response = self.post('/api/v1/goals/suggestions/', {'height_cm': 10, 'weight_kg': 65})
        self.assertEqual(response.status_code, 400, response.content)


def png_upload():
    image = Image.new('RGB', (320, 240), 'purple')
    buffer = BytesIO()
    image.save(buffer, format='PNG')
    return SimpleUploadedFile('meal.png', buffer.getvalue(), content_type='image/png')


class NormalizeCandidatesTests(TestCase):
    def test_clamps_sorts_and_drops_invalid(self):
        result = normalize_candidates([
            {'name': 'Low', 'category': 'Dish', 'confidence': -1},
            {'name': 'Valid', 'category': 'Dish', 'confidence': 0.7},
            {'name': 'High', 'confidence': 9},
            'not-a-dict',
            {'confidence': 0.5},
        ])
        self.assertEqual(result[0]['name'], 'High')
        self.assertEqual(result[0]['confidence'], 1.0)
        self.assertEqual(result[1]['name'], 'Valid')
        self.assertEqual(result[2]['name'], 'Low')
        self.assertEqual(result[2]['confidence'], 0.0)
        self.assertTrue(all('name' in item for item in result))


class RecognitionCatalogMatchingTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email='labels@example.com', password='secure-pass-123')

    def test_model_spelling_alias_matches_catalog_food(self):
        food = Food.objects.create(created_by=self.user, name='Paratha', category='Bread', kcal_100g=300,
                                   protein_100g=7, carbs_100g=45, fat_100g=10,
                                   source='Test fixture')
        matches = matched_catalog_foods(
            [{'name': 'Paratha', 'model_label': 'porota', 'confidence': 0.8}], self.user)
        self.assertEqual(matches['Paratha'], str(food.id))

    def test_seeded_model_food_wins_over_looser_user_alias(self):
        food = Food.objects.create(created_by=self.user, name='Ilish bhaja', category='Fish', kcal_100g=250,
                                   protein_100g=22, carbs_100g=1, fat_100g=18,
                                   source='Test fixture')
        FoodAlias.objects.create(food=food, alias='hilsha fish', language='en')
        matches = matched_catalog_foods(
            [{'name': 'Hilsa fish', 'model_label': 'hilsha_fish', 'confidence': 0.8}], self.user)
        catalog_food = Food.objects.get(created_by=None, name='Hilsa fish')
        self.assertEqual(matches['Hilsa fish'], str(catalog_food.id))


@override_settings(AI_TIMEOUT_SECONDS=5, AI_PROVIDER='')
class RecognitionTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = Client(enforce_csrf_checks=True)
        self.user = User.objects.create_user(email='a@example.com', password='secure-pass-123')
        Profile.objects.create(user=self.user)
        self.food = Food.objects.create(name='Grilled chicken salad', category='Dish', kcal_100g=150,
            protein_100g=20, carbs_100g=6, fat_100g=5, source='Test fixture')
        self.client.get('/api/v1/auth/csrf/')
        self.csrf = self.client.cookies['csrftoken'].value
        login = self.client.post('/api/v1/auth/login/',
            data=json.dumps({'email': self.user.email, 'password': 'secure-pass-123'}),
            content_type='application/json', HTTP_X_CSRFTOKEN=self.csrf)
        self.assertEqual(login.status_code, 200, login.content)
        self.client.get('/api/v1/auth/csrf/')
        self.csrf = self.client.cookies['csrftoken'].value

    def upload(self):
        return self.client.post('/api/v1/recognitions/', data={'image': png_upload()}, HTTP_X_CSRFTOKEN=self.csrf)

    def test_recognition_off_by_default_stays_manual(self):
        response = self.upload()
        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        self.assertEqual(body['status'], 'unavailable')
        self.assertEqual(body['error_code'], 'MODEL_NOT_CONFIGURED')
        self.assertEqual(body['candidates'], [])
        self.assertEqual(body['message'], 'Recognition is not configured yet. Add food manually.')
        self.assertTrue(FoodImage.objects.get(pk=body['image_id']).file.name)

    @override_settings(AI_PROVIDER='openai', AI_VISION_MODEL='test-model',
                       AI_API_KEYS={'openai': 'test-key', 'gemini': ''})
    def test_openai_provider_returns_candidates_and_matches_food(self):
        content = json.dumps({'candidates': [
            {'name': self.food.name, 'category': 'Dish', 'confidence': 0.92},
            {'name': 'Other dish', 'category': 'Dish', 'confidence': 0.5},
        ]})
        canned = {'choices': [{'message': {'content': content}}]}
        with patch('core.services._provider_request', return_value=canned) as request_mock:
            response = self.upload()
        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        self.assertEqual(body['status'], 'completed')
        self.assertEqual(body['model_version'], 'openai:test-model')
        self.assertEqual(body['error_code'], '')
        self.assertEqual(body['candidates'][0]['name'], self.food.name)
        self.assertEqual(body['candidates'][0]['food_id'], str(self.food.id))
        self.assertEqual(body['candidates'][1]['confidence'], 0.5)
        self.assertIsNone(body['candidates'][1]['food_id'])
        self.assertEqual(len(response.json()['candidates']), 2)
        request_mock.assert_called_once()
        request_body = request_mock.call_args.args[2].decode('utf-8', 'ignore')
        self.assertNotIn('test-key', request_body)
        self.assertIn('data:image/jpeg;base64,', request_body)
        prediction = FoodPrediction.objects.get(pk=body['id'])
        self.assertEqual(prediction.status, 'completed')
        self.assertEqual(RecognitionResult.objects.filter(session=prediction).count(), 2)
        self.assertEqual(body['candidates'][0]['result_id'],
                         str(RecognitionResult.objects.get(session=prediction, rank=1).id))

    @override_settings(AI_PROVIDER='gemini', AI_VISION_MODEL='test-model',
                       AI_API_KEYS={'openai': '', 'gemini': 'test-key'})
    def test_gemini_provider_returns_candidates(self):
        content = json.dumps({'candidates': [{'name': self.food.name, 'category': 'Dish', 'confidence': 0.8}]})
        canned = {'candidates': [{'content': {'parts': [{'text': content}]}}]}
        with patch('core.services._provider_request', return_value=canned):
            response = self.upload()
        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        self.assertEqual(body['status'], 'completed')
        self.assertEqual(body['model_version'], 'gemini:test-model')
        self.assertEqual(body['candidates'][0]['food_id'], str(self.food.id))
        self.assertIsNone(body['candidates'][0].get('grams'))

    @override_settings(AI_PROVIDER='openai', AI_VISION_MODEL='test-model',
                       AI_API_KEYS={'openai': 'test-key', 'gemini': ''})
    def test_provider_failure_keeps_prediction_and_manual_logging(self):
        with patch('core.services._provider_request', side_effect=ProviderError('PROVIDER_ERROR')):
            response = self.upload()
        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        self.assertEqual(body['status'], 'failed')
        self.assertEqual(body['error_code'], 'PROVIDER_ERROR')
        self.assertEqual(body['candidates'], [])
        detail = self.client.get(f"/api/v1/recognitions/{body['id']}/")
        self.assertEqual(detail.json()['error_code'], 'PROVIDER_ERROR')
        # Manual path still works: meal saved with this image computes totals on server.
        meal_response = self.client.post('/api/v1/meals/',
            data=json.dumps({'eaten_at': timezone.now().isoformat(), 'meal_type': 'lunch',
                             'image_id': body['image_id'],
                             'items': [{'food_id': str(self.food.id), 'grams': 200}]}),
            content_type='application/json', HTTP_X_CSRFTOKEN=self.csrf)
        self.assertEqual(meal_response.status_code, 201, meal_response.content)
        self.assertEqual(Decimal(meal_response.json()['totals']['kcal']), Decimal('300.00'))

    @override_settings(AI_PROVIDER='openai', AI_API_KEYS={'openai': '', 'gemini': ''})
    def test_provider_selected_without_key_stays_unavailable(self):
        response = self.upload()
        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        self.assertEqual(body['status'], 'unavailable')
        self.assertEqual(body['error_code'], 'MODEL_NOT_CONFIGURED')

    @override_settings(AI_PROVIDER='nonsense', AI_VISION_MODEL='bogus-model',
                       AI_API_KEYS={'openai': 'test-key', 'gemini': 'test-key'})
    def test_unknown_provider_value_is_off(self):
        response = self.upload()
        body = response.json()
        self.assertEqual(body['status'], 'unavailable')
        self.assertEqual(body['error_code'], 'MODEL_NOT_CONFIGURED')

    @override_settings(AI_PROVIDER='local', AI_API_KEYS={})
    def test_local_recognition_persists_candidates_without_cloud_call(self):
        candidates = [{'name': self.food.name, 'category': 'Dish', 'confidence': 0.912, 'food_id': None}]
        with patch('core.local_recognition.local_candidates', return_value=(candidates, 'local:banglafoodnet:test')), \
                patch('core.services._provider_request') as cloud, \
                patch('core.views.provider_image_bytes') as compress:
            response = self.upload()
        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        self.assertEqual(body['status'], 'completed')
        self.assertEqual(body['model_version'], 'local:banglafoodnet:test')
        self.assertEqual(body['candidates'][0]['food_id'], str(self.food.id))
        saved = RecognitionResult.objects.get(pk=body['candidates'][0]['result_id'])
        self.assertEqual(saved.confidence, Decimal('0.912'))
        self.assertNotIn('grams', body['candidates'][0])
        cloud.assert_not_called()
        compress.assert_not_called()

        custom_food_res = self.client.post(
            '/api/v1/foods/',
            data=json.dumps({
                'name': 'Old Dhaka Mutton Kacchi Biryani',
                'category': 'My foods',
                'kcal_100g': '193.9',
                'protein_100g': '10.6',
                'carbs_100g': '15.5',
                'fat_100g': '9.5',
            }),
            content_type='application/json',
            HTTP_X_CSRFTOKEN=self.csrf,
        )
        self.assertEqual(custom_food_res.status_code, 201, custom_food_res.content)
        custom_food_id = custom_food_res.json()['id']

        meal_res = self.client.post(
            '/api/v1/meals/',
            data=json.dumps({
                'eaten_at': timezone.now().isoformat(),
                'meal_type': 'lunch',
                'notes': 'This is a test food',
                'image_id': body['image_id'],
                'items': [{
                    'food_id': custom_food_id,
                    'grams': 380,
                    'recognition_result_id': body['candidates'][0]['result_id'],
                }],
            }),
            content_type='application/json',
            HTTP_X_CSRFTOKEN=self.csrf,
        )
        self.assertEqual(meal_res.status_code, 201, meal_res.content)
        self.assertEqual(meal_res.json()['items'][0]['recognition_result'], saved.id)

    @override_settings(AI_PROVIDER='local', AI_LOCAL_CHECKPOINT='/missing/mealsense-checkpoint.pth')
    def test_missing_local_checkpoint_keeps_manual_logging_available(self):
        with patch('core.services._provider_request') as cloud:
            response = self.upload()
        body = response.json()
        self.assertEqual(body['status'], 'unavailable')
        self.assertEqual(body['error_code'], 'MODEL_NOT_CONFIGURED')
        self.assertTrue(FoodImage.objects.filter(pk=body['image_id']).exists())
        cloud.assert_not_called()

    @override_settings(AI_PROVIDER='local')
    def test_local_failure_is_saved_without_cloud_fallback(self):
        from .local_recognition import LocalModelError
        with patch('core.local_recognition.local_candidates', side_effect=LocalModelError('LOCAL_MODEL_ERROR')), \
                patch('core.services._provider_request') as cloud:
            response = self.upload()
        body = response.json()
        self.assertEqual(body['status'], 'failed')
        self.assertEqual(body['error_code'], 'LOCAL_MODEL_ERROR')
        self.assertEqual(body['candidates'], [])
        self.assertEqual(self.client.get(f"/api/v1/recognitions/{body['id']}/").json()['status'], 'failed')
        cloud.assert_not_called()


def csrf_client():
    client = Client(enforce_csrf_checks=True)
    client.get('/api/v1/auth/csrf/')
    return client, client.cookies['csrftoken'].value


class DoctorAccessTests(TestCase):
    """Public doctor request page, patient consent, token-gated history/analytics."""

    def setUp(self):
        cache.clear()
        self.client = Client(enforce_csrf_checks=True)
        self.patient = User.objects.create_user(email='rahim@example.com', password='secure-pass-123',
                                                display_name='Rahim Uddin')
        Profile.objects.create(user=self.patient, timezone='Asia/Dhaka', phone='8801712345678')
        self.stranger = User.objects.create_user(email='stranger@example.com', password='secure-pass-123')
        Profile.objects.create(user=self.stranger, timezone='UTC')
        self.rice = Food.objects.create(name='Rice', category='Grain', kcal_100g=130,
                                        protein_100g=2.7, carbs_100g=28, fat_100g=0.3, source='Test fixture')
        self.dal = Food.objects.create(name='Dal', category='Dish', kcal_100g=120,
                                       protein_100g=6, carbs_100g=15, fat_100g=3, source='Test fixture')
        self.client.get('/api/v1/auth/csrf/')
        self.csrf = self.client.cookies['csrftoken'].value
        login = self.client.post('/api/v1/auth/login/', data=json.dumps(
            {'identifier': self.patient.email, 'password': 'secure-pass-123'}),
            content_type='application/json', HTTP_X_CSRFTOKEN=self.csrf)
        self.assertEqual(login.status_code, 200, login.content)
        self.client.get('/api/v1/auth/csrf/')
        self.csrf = self.client.cookies['csrftoken'].value
        self.doctor_client, self.doctor_csrf = csrf_client()
        self.other_client, self.other_csrf = csrf_client()
        self.seed_meals()

    def seed_meals(self):
        logged = [
            ('2026-01-15T10:00:00+00:00', 'lunch', [(self.rice, 200), (self.dal, 100)]),
            # 19:00 UTC on Jan 31 is 01:00 Feb 1 in Dhaka: must land in February.
            ('2026-01-31T19:00:00+00:00', 'breakfast', [(self.rice, 150)]),
            ('2026-02-10T06:00:00+00:00', 'dinner', [(self.dal, 200), (self.rice, 100)]),
        ]
        for eaten_at, meal_type, items in logged:
            response = self.client.post('/api/v1/meals/', data=json.dumps({
                'eaten_at': eaten_at, 'meal_type': meal_type,
                'notes': 'private note', 'items': [{'food_id': str(food.id), 'grams': grams}
                                                   for food, grams in items]}),
                content_type='application/json', HTTP_X_CSRFTOKEN=self.csrf)
            self.assertEqual(response.status_code, 201, response.content)

    def request_access(self, identifier='rahim@example.com', doctor_name='Dr. Karim'):
        return self.doctor_client.post('/api/v1/doctor-access/request/',
                                       data=json.dumps({'identifier': identifier, 'doctor_name': doctor_name}),
                                       content_type='application/json', HTTP_X_CSRFTOKEN=self.doctor_csrf)

    def approve(self):
        listing = self.client.get('/api/v1/doctor-access/requests/').json()
        return self.client.post(f"/api/v1/doctor-access/requests/{listing[0]['id']}/decision/",
                                data=json.dumps({'action': 'approve'}),
                                content_type='application/json', HTTP_X_CSRFTOKEN=self.csrf)

    def test_request_creation_is_public_and_generates_token(self):
        response = self.request_access()
        self.assertEqual(response.status_code, 202, response.content)
        self.assertEqual(response.json()['status'], 'pending')
        token = response.json()['token']
        self.assertTrue(token)
        request = DoctorAccessRequest.objects.get(patient=self.patient)
        self.assertEqual(request.identifier_type, 'email')
        self.assertEqual(request.identifier, 'rahim@example.com')
        self.assertEqual(request.view_token, token)
        self.assertFalse(request.is_active())

    def test_request_reuses_pending_token_for_same_doctor(self):
        first = self.request_access()
        second = self.request_access()
        self.assertEqual(first.json()['token'], second.json()['token'])
        self.assertEqual(DoctorAccessRequest.objects.count(), 1)

    def test_unknown_patient_gets_generic_response_without_token(self):
        matched = self.request_access()
        unmatched = self.request_access(identifier='nobody@example.com')
        self.assertEqual(unmatched.status_code, 202, unmatched.content)
        self.assertTrue(isinstance(unmatched.json()['token'], str) and len(unmatched.json()['token']) >= 32)
        self.assertEqual(unmatched.json()['message'], DOCTOR_REQUEST_PENDING_MESSAGE)
        self.assertEqual(unmatched.json()['message'], matched.json()['message'])
        self.assertEqual(DoctorAccessRequest.objects.count(), 1)

    def test_request_requires_name_and_valid_identifier(self):
        missing_name = self.request_access(doctor_name='   ')
        self.assertEqual(missing_name.status_code, 400)
        bad_email = self.request_access(identifier='not-an-email')
        self.assertEqual(bad_email.status_code, 400)
        bad_phone = self.request_access(identifier='123')
        self.assertEqual(bad_phone.status_code, 400)

    def test_phone_request_normalizes_digits(self):
        response = self.request_access(identifier='+880 1712-345678')
        self.assertEqual(response.status_code, 202, response.content)
        request = DoctorAccessRequest.objects.get()
        self.assertEqual(request.identifier_type, 'phone')
        self.assertEqual(request.identifier, '8801712345678')

    def test_patient_decision_and_token_gated_view(self):
        token = self.request_access().json()['token']
        listing = self.client.get('/api/v1/doctor-access/requests/').json()
        self.assertEqual(listing[0]['doctor_name'], 'Dr. Karim')
        self.assertNotIn('view_token', listing[0])
        decision = self.approve()
        self.assertEqual(decision.status_code, 200, decision.content)
        self.assertEqual(decision.json()['status'], 'approved')
        request = DoctorAccessRequest.objects.get()
        self.assertIsNotNone(request.expires_at)
        self.assertTrue(request.is_active())

        status = self.doctor_client.get('/api/v1/doctor-access/view/status/', HTTP_X_DOCTOR_ACCESS_TOKEN=token)
        body = status.json()
        self.assertEqual(body['status'], 'approved')
        self.assertTrue(body['active'])
        self.assertEqual(body['patient_name'], 'Rahim Uddin')
        self.assertEqual(body['patient_timezone'], 'Asia/Dhaka')

        history = self.doctor_client.get('/api/v1/doctor-access/view/history/', HTTP_X_DOCTOR_ACCESS_TOKEN=token)
        self.assertEqual(history.status_code, 200, history.content)
        data = history.json()
        self.assertEqual(data['count'], 3)
        # Newest first; the meal logged at 19:00 UTC Jan 31 is Feb 1 in Dhaka.
        self.assertEqual([meal['local_date'] for meal in data['meals']],
                         ['2026-02-10', '2026-02-01', '2026-01-15'])
        meal = data['meals'][0]
        self.assertEqual(set(meal), {'id', 'eaten_at', 'local_date', 'meal_type', 'items', 'totals'})
        self.assertEqual(set(meal['items'][0]),
                         {'food_name', 'grams', 'kcal', 'protein_g', 'carbs_g', 'fat_g',
                          'nutrition_source_snapshot'})
        self.assertEqual(meal['totals']['kcal'], '370.00')
        # Photos and notes never cross the boundary.
        self.assertNotIn('notes', meal)
        self.assertNotIn('image', meal)

    def test_analytics_frequency_monthly_and_custom_range(self):
        token = self.request_access().json()['token']
        self.approve()
        analytics = self.doctor_client.get('/api/v1/doctor-access/view/analytics/',
                                           HTTP_X_DOCTOR_ACCESS_TOKEN=token).json()
        self.assertEqual(Decimal(analytics['totals']['kcal']), Decimal('945.00'))
        self.assertEqual(analytics['meals_logged'], 3)
        self.assertEqual(analytics['items_logged'], 5)
        self.assertEqual(analytics['logged_days'], 3)
        self.assertEqual(Decimal(analytics['avg_kcal_per_logged_day']), Decimal('315'))
        self.assertEqual(analytics['most_consumed'][0]['food_name'], 'Rice')
        self.assertEqual(Decimal(analytics['most_consumed'][0]['grams']), Decimal('450.00'))
        self.assertEqual(analytics['food_frequency'][0]['food_name'], 'Rice')
        self.assertEqual(analytics['food_frequency'][0]['times'], 3)
        self.assertEqual([row['month'] for row in analytics['monthly']], ['2026-01', '2026-02'])
        january, february = analytics['monthly']
        self.assertEqual(Decimal(january['kcal']), Decimal('380.00'))
        self.assertEqual(january['meals'], 1)
        self.assertEqual(Decimal(february['kcal']), Decimal('565.00'))
        self.assertEqual(february['meals'], 2)
        self.assertEqual({row['meal_type'] for row in analytics['by_meal_type']},
                         {'lunch', 'breakfast', 'dinner'})

        ranged = self.doctor_client.get(
            '/api/v1/doctor-access/view/analytics/?from=2026-02-01&to=2026-02-28',
            HTTP_X_DOCTOR_ACCESS_TOKEN=token).json()
        self.assertEqual(ranged['range'], {'from': '2026-02-01', 'to': '2026-02-28'})
        self.assertEqual([row['month'] for row in ranged['monthly']], ['2026-02'])
        self.assertEqual(ranged['meals_logged'], 2)
        history = self.doctor_client.get(
            '/api/v1/doctor-access/view/history/?from=2026-02-01&to=2026-02-28',
            HTTP_X_DOCTOR_ACCESS_TOKEN=token).json()
        self.assertEqual(history['count'], 2)

    def test_history_pagination(self):
        token = self.request_access().json()['token']
        self.approve()
        page = self.doctor_client.get('/api/v1/doctor-access/view/history/?limit=2&offset=2',
                                      HTTP_X_DOCTOR_ACCESS_TOKEN=token).json()
        self.assertEqual(page['count'], 3)
        self.assertEqual(len(page['meals']), 1)
        self.assertEqual(page['meals'][0]['local_date'], '2026-01-15')

    def test_unknown_token_is_not_found(self):
        self.assertEqual(
            self.doctor_client.get('/api/v1/doctor-access/view/status/',
                                   HTTP_X_DOCTOR_ACCESS_TOKEN='bogus').status_code, 404)

    def test_denied_request_blocks_access(self):
        token = self.request_access(doctor_name='Dr. Other').json()['token']
        listing = self.client.get('/api/v1/doctor-access/requests/').json()
        denied = self.client.post(f"/api/v1/doctor-access/requests/{listing[0]['id']}/decision/",
                                  data=json.dumps({'action': 'deny'}),
                                  content_type='application/json', HTTP_X_CSRFTOKEN=self.csrf)
        self.assertEqual(denied.status_code, 200)
        status = self.doctor_client.get('/api/v1/doctor-access/view/status/',
                                        HTTP_X_DOCTOR_ACCESS_TOKEN=token).json()
        self.assertEqual(status['status'], 'denied')
        self.assertFalse(status['active'])
        self.assertEqual(
            self.doctor_client.get('/api/v1/doctor-access/view/history/',
                                   HTTP_X_DOCTOR_ACCESS_TOKEN=token).status_code, 403)

    def test_revoke_then_reapprove_rotates_token(self):
        token = self.request_access().json()['token']
        self.approve()
        listing = self.client.get('/api/v1/doctor-access/requests/').json()
        request_id = listing[0]['id']
        revoked = self.client.post(f'/api/v1/doctor-access/requests/{request_id}/decision/',
                                   data=json.dumps({'action': 'revoke'}),
                                   content_type='application/json', HTTP_X_CSRFTOKEN=self.csrf)
        self.assertEqual(revoked.status_code, 200)
        self.assertEqual(
            self.doctor_client.get('/api/v1/doctor-access/view/history/',
                                   HTTP_X_DOCTOR_ACCESS_TOKEN=token).status_code, 403)
        renewed = self.client.post(f'/api/v1/doctor-access/requests/{request_id}/decision/',
                                   data=json.dumps({'action': 'approve'}),
                                   content_type='application/json', HTTP_X_CSRFTOKEN=self.csrf)
        self.assertEqual(renewed.status_code, 200)
        request = DoctorAccessRequest.objects.get()
        self.assertTrue(request.is_active())
        # Re-approval must never resurrect the token the doctor held while the
        # share was active: a leaked copy stays useless after revocation.
        self.assertNotEqual(request.view_token, token)
        self.assertEqual(len(request.view_token), len(token))
        self.assertEqual(
            self.doctor_client.get('/api/v1/doctor-access/view/history/',
                                   HTTP_X_DOCTOR_ACCESS_TOKEN=token).status_code, 404)
        self.assertEqual(
            self.doctor_client.get('/api/v1/doctor-access/view/status/',
                                   HTTP_X_DOCTOR_ACCESS_TOKEN=request.view_token).json()['active'],
            True)

    def test_expired_request_reads_as_expired_and_renewable(self):
        token = self.request_access().json()['token']
        self.approve()
        request = DoctorAccessRequest.objects.get()
        request.expires_at = timezone.now() - timedelta(hours=1)
        request.save(update_fields=['expires_at'])
        self.assertFalse(request.is_active())
        status = self.doctor_client.get('/api/v1/doctor-access/view/status/',
                                        HTTP_X_DOCTOR_ACCESS_TOKEN=token).json()
        self.assertEqual(status['status'], 'expired')
        self.assertEqual(
            self.doctor_client.get('/api/v1/doctor-access/view/analytics/',
                                   HTTP_X_DOCTOR_ACCESS_TOKEN=token).status_code, 403)
        renewed = self.approve()
        self.assertEqual(renewed.status_code, 200, renewed.content)
        self.assertTrue(DoctorAccessRequest.objects.get().is_active())

    def test_other_user_cannot_see_or_decide_requests(self):
        self.request_access()
        login = self.other_client.post('/api/v1/auth/login/', data=json.dumps(
            {'identifier': self.stranger.email, 'password': 'secure-pass-123'}),
            content_type='application/json', HTTP_X_CSRFTOKEN=self.other_csrf)
        self.assertEqual(login.status_code, 200, login.content)
        self.other_client.get('/api/v1/auth/csrf/')
        self.other_csrf = self.other_client.cookies['csrftoken'].value
        listing = self.other_client.get('/api/v1/doctor-access/requests/').json()
        self.assertEqual(listing, [])
        request_id = self.client.get('/api/v1/doctor-access/requests/').json()[0]['id']
        response = self.other_client.post(f'/api/v1/doctor-access/requests/{request_id}/decision/',
                                          data=json.dumps({'action': 'approve'}),
                                          content_type='application/json', HTTP_X_CSRFTOKEN=self.other_csrf)
        self.assertEqual(response.status_code, 404)

    def test_public_request_requires_csrf(self):
        bare = Client(enforce_csrf_checks=True)
        response = bare.post('/api/v1/doctor-access/request/',
                             data=json.dumps({'identifier': 'rahim@example.com', 'doctor_name': 'Dr. Karim'}),
                             content_type='application/json')
        self.assertEqual(response.status_code, 403)

    def test_patient_meal_range_filter(self):
        meals = self.client.get('/api/v1/meals/?from=2026-02-01&to=2026-02-28').json()
        self.assertEqual(len(meals), 2)
        invalid = self.client.get('/api/v1/meals/?from=yesterday')
        self.assertEqual(invalid.status_code, 400)

    def test_profile_phone_saved_and_clearable(self):
        response = self.client.patch('/api/v1/users/me/',
                                     data=json.dumps({'profile': {'phone': '880 1712-999999'}}),
                                     content_type='application/json', HTTP_X_CSRFTOKEN=self.csrf)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(Profile.objects.get(user=self.patient).phone, '8801712999999')
        cleared = self.client.patch('/api/v1/users/me/',
                                    data=json.dumps({'profile': {'phone': ''}}),
                                    content_type='application/json', HTTP_X_CSRFTOKEN=self.csrf)
        self.assertEqual(cleared.status_code, 200)
        self.assertIsNone(Profile.objects.get(user=self.patient).phone)

    def test_duplicate_phone_returns_400_instead_of_500(self):
        self.other_client.post('/api/v1/auth/login/', data=json.dumps(
            {'identifier': self.stranger.email, 'password': 'secure-pass-123'}),
            content_type='application/json', HTTP_X_CSRFTOKEN=self.other_csrf)
        self.other_client.get('/api/v1/auth/csrf/')
        self.other_csrf = self.other_client.cookies['csrftoken'].value
        dup = self.other_client.patch('/api/v1/users/me/',
                                      data=json.dumps({'profile': {'phone': '+880 1712-345678'}}),
                                      content_type='application/json', HTTP_X_CSRFTOKEN=self.other_csrf)
        self.assertEqual(dup.status_code, 400, dup.content)

    def test_food_log_audit_and_daily_summary_and_weekly_view(self):
        weekly = self.client.get('/api/v1/nutrition/weekly/')
        self.assertEqual(weekly.status_code, 200)
        self.assertEqual(len(weekly.json()), 7)

        missing_nutr = self.client.post('/api/v1/foods/',
                                        data=json.dumps({'name': 'Incomplete Food', 'kcal_100g': '100'}),
                                        content_type='application/json', HTTP_X_CSRFTOKEN=self.csrf)
        self.assertEqual(missing_nutr.status_code, 400)

        created = self.client.post('/api/v1/meals/',
                                   data=json.dumps({
                                       'eaten_at': timezone.now().isoformat(),
                                       'meal_type': 'lunch',
                                       'items': [{'food_id': str(self.rice.id), 'grams': 200}],
                                   }),
                                   content_type='application/json', HTTP_X_CSRFTOKEN=self.csrf)
        self.assertEqual(created.status_code, 201, created.content)
        meal_id = created.json()['id']
        self.assertTrue(FoodLog.objects.filter(user=self.patient, meal_id_snapshot=meal_id, action='created').exists())
        self.assertTrue(DailyNutritionSummary.objects.filter(user=self.patient).exists())

        deleted = self.client.delete(f'/api/v1/meals/{meal_id}/', HTTP_X_CSRFTOKEN=self.csrf)
        self.assertEqual(deleted.status_code, 204)
        self.assertTrue(FoodLog.objects.filter(user=self.patient, meal_id_snapshot=meal_id, action='deleted').exists())

    def test_recognition_detail_rejects_untrusted_checkpoint_parameter(self):
        with tempfile.TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=media_root):
            buf = BytesIO()
            Image.new('RGB', (64, 64), 'green').save(buf, format='JPEG')
            upload = SimpleUploadedFile('test.jpg', buf.getvalue(), content_type='image/jpeg')
            rec_res = self.client.post('/api/v1/recognitions/', {'image': upload}, HTTP_X_CSRFTOKEN=self.csrf)
            self.assertEqual(rec_res.status_code, 201, rec_res.content)
            rec_id = rec_res.json()['id']
            bad_ckpt = self.client.post(
                f'/api/v1/recognitions/{rec_id}/',
                data=json.dumps({'action': 'analyze', 'checkpoint': '/tmp/evil_checkpoint'}),
                content_type='application/json',
                HTTP_X_CSRFTOKEN=self.csrf,
            )
            self.assertEqual(bad_ckpt.status_code, 400, bad_ckpt.content)
