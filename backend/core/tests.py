import json
import tempfile
from decimal import Decimal
from io import BytesIO
from unittest.mock import patch
from uuid import uuid4
from PIL import Image
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.utils import timezone
from .models import Food, FoodImage, FoodPrediction, Meal, Profile, User
from .services import ProviderError, normalize_candidates


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


@override_settings(AI_TIMEOUT_SECONDS=5)
class RecognitionTests(TestCase):
    def setUp(self):
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
