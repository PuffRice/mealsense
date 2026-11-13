from io import BytesIO
from pathlib import Path
from unittest import skipUnless

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase, override_settings
from PIL import Image

from .dinov3_recognition import _load_model, predict_food, recognize_dinov3
from .models import RecognitionResult, User


ARTIFACT = settings.BASE_DIR / 'ml_models/dinov3/checkpoint.pth'


@skipUnless(ARTIFACT.is_file(), 'DINOv3 deployment checkpoint not installed')
class DINOv3Tests(SimpleTestCase):
    @override_settings(AI_DINOV3_DEVICE='cpu')
    def test_cpu_inference_mapping_and_cache(self):
        picture = BytesIO()
        Image.new('RGB', (320, 240), (120, 90, 30)).save(picture, format='PNG')
        _load_model.cache_clear()
        predictions = predict_food(picture.getvalue(), top_k=3)
        self.assertEqual(len(predictions), 3)
        self.assertEqual(_load_model.cache_info().misses, 1)
        self.assertEqual(predictions, predict_food(picture.getvalue(), top_k=3))
        self.assertEqual(_load_model.cache_info().hits, 1)
        self.assertTrue(all(0 <= item['confidence'] <= 1 for item in predictions))
        self.assertEqual([item['confidence'] for item in predictions],
                         sorted((item['confidence'] for item in predictions), reverse=True))

    def test_bad_image_and_top_k(self):
        with self.assertRaises(ValueError):
            predict_food(b'bad', top_k=0)
        with self.assertRaises(ValueError):
            predict_food(b'bad', top_k=1)

    @override_settings(AI_DINOV3_DEVICE='cpu')
    def test_provider_contract(self):
        picture = BytesIO()
        Image.new('RGB', (224, 224), 'red').save(picture, format='JPEG')
        result = recognize_dinov3(picture.getvalue())
        self.assertEqual(result['status'], 'completed', result)
        self.assertEqual(len(result['candidates']), settings.AI_DINOV3_TOP_K)


@skipUnless(ARTIFACT.is_file(), 'DINOv3 deployment checkpoint not installed')
@override_settings(AI_PROVIDER='dinov3', AI_DINOV3_DEVICE='cpu')
class DINOv3ApiTests(TestCase):
    def test_authenticated_multipart_upload_persists_results(self):
        import tempfile
        with tempfile.TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=media_root):
            user = User.objects.create_user(email='dino@example.com', password='secure-pass-123')
            self.client.force_login(user)
            picture = BytesIO()
            Image.new('RGB', (224, 224), 'red').save(picture, format='PNG')
            upload = SimpleUploadedFile('dish.png', picture.getvalue(), content_type='image/png')
            response = self.client.post('/api/v1/recognitions/', {'image': upload})
            self.assertEqual(response.status_code, 201, response.content)
            body = response.json()
            self.assertEqual(body['status'], 'completed', body)
            self.assertEqual(len(body['candidates']), settings.AI_DINOV3_TOP_K)
            self.assertEqual(RecognitionResult.objects.filter(session_id=body['id']).count(),
                             settings.AI_DINOV3_TOP_K)
