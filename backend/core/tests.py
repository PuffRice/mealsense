import json
import tempfile
from decimal import Decimal
from io import BytesIO
from uuid import uuid4
from PIL import Image
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.utils import timezone
from .models import Food, FoodImage, Meal, Profile, User


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
