"""Optional runtime checks; the base API test suite needs no torch install."""
from importlib.util import find_spec
from io import BytesIO
import tempfile
from unittest import skipUnless
from unittest.mock import patch

from django.conf import settings
from django.test import SimpleTestCase, override_settings
from PIL import Image

from .local_recognition import _load_model, local_candidates, recognize_locally

HAS_RUNTIME = find_spec('torch') is not None and find_spec('torchvision') is not None
ARTIFACT = settings.BASE_DIR / 'model_artifacts/banglafoodnet/banglafoodnet_finetuned.pth'


class LocalFailureTests(SimpleTestCase):
    def test_missing_dependencies_return_unavailable_without_cloud(self):
        with tempfile.NamedTemporaryFile() as source, \
                override_settings(AI_LOCAL_CHECKPOINT=source.name), \
                patch('core.local_recognition._load_model', side_effect=ImportError):
            result = recognize_locally(b'image')
        self.assertEqual(result['status'], 'unavailable')
        self.assertEqual(result['error_code'], 'LOCAL_DEPENDENCIES_MISSING')
        self.assertEqual(result['candidates'], [])


@skipUnless(HAS_RUNTIME, 'Install requirements-local.txt for runtime checks')
class LocalRuntimeTests(SimpleTestCase):
    def test_checkpoint_label_order_determines_ranked_names(self):
        import torch
        image = BytesIO()
        Image.new('RGB', (10, 20)).save(image, format='PNG')
        # Deliberately non-alphabetical labels catch accidental sorting.
        labels = ('yogurt', 'egg_omlete', 'morog_polao')
        model = lambda tensor: {'dish': torch.tensor([[0., 4., 2.]])}
        transform = lambda image: torch.zeros(3, 160, 160)
        with tempfile.NamedTemporaryFile() as source, \
                override_settings(AI_LOCAL_CHECKPOINT=source.name), \
                patch('core.local_recognition._load_model',
                      return_value=(model, transform, labels, 'cpu', 'local:test')):
            candidates, version = local_candidates(image.getvalue())
        self.assertEqual([c['name'] for c in candidates], ['Egg omelette', 'Morog polao', 'Yogurt'])
        self.assertAlmostEqual(candidates[0]['confidence'], 0.867, places=3)
        self.assertEqual(version, 'local:test')
        self.assertTrue(all(set(c) == {'name', 'category', 'confidence', 'food_id'} for c in candidates))

    def test_corrupt_checkpoint_returns_failed(self):
        with tempfile.NamedTemporaryFile() as source:
            source.write(b'not a torch checkpoint')
            source.flush()
            with override_settings(AI_LOCAL_CHECKPOINT=source.name), \
                    self.assertLogs('core.local_recognition', level='ERROR'):
                result = recognize_locally(b'image')
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(result['error_code'], 'LOCAL_MODEL_ERROR')

    @skipUnless(ARTIFACT.is_file(), 'Download the supplied checkpoint for inference smoke test')
    @override_settings(AI_LOCAL_CHECKPOINT=str(ARTIFACT), AI_LOCAL_DEVICE='cpu')
    def test_supplied_checkpoint_runs_offline_and_reuses_loaded_model(self):
        image = BytesIO()
        Image.new('RGB', (320, 240), (100, 150, 200)).save(image, format='PNG')
        _load_model.cache_clear()
        with patch('urllib.request.urlopen', side_effect=AssertionError('Inference must stay offline')), \
                patch('torch.hub.download_url_to_file', side_effect=AssertionError('No pretrained download')):
            result = recognize_locally(image.getvalue())
            repeated = recognize_locally(image.getvalue())
        self.assertEqual(result['status'], 'completed', result)
        self.assertEqual(result, repeated)
        self.assertEqual(result['model_version'], 'local:banglafoodnet:b210a967ecc5c65f')
        self.assertEqual(len(result['candidates']), 5)
        self.assertEqual(_load_model.cache_info().misses, 1)
        self.assertEqual(_load_model.cache_info().hits, 1)
        scores = [c['confidence'] for c in result['candidates']]
        self.assertEqual(scores, sorted(scores, reverse=True))
        self.assertTrue(all(0 <= score <= 1 for score in scores))
