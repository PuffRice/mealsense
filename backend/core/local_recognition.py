"""Lazy, cached inference for the supplied BanglaFoodNet checkpoint."""
from functools import lru_cache
from hashlib import sha256
from io import BytesIO
import logging
from pathlib import Path
from threading import Lock

from django.conf import settings
from PIL import Image, ImageOps
from .recognition_labels import model_display_name

logger = logging.getLogger(__name__)
_load_lock = Lock()


class LocalModelError(Exception):
    def __init__(self, code, status='failed'):
        self.code = code
        self.status = status


@lru_cache(maxsize=1)
def _load_model(path, modified_ns, size, device_name):
    # Imported only for local recognition; cloud/manual installs need no torch.
    import torch
    from torchvision import transforms
    from .banglafoodnet import BanglaFoodNet

    # Never enable arbitrary pickle execution, even for a user-provided checkpoint.
    checkpoint = torch.load(path, map_location='cpu', weights_only=True)
    labels = checkpoint['class_names']
    image_size = checkpoint['img_size']
    if (not isinstance(labels, (list, tuple)) or not labels
            or any(not isinstance(label, str) or not label.strip() for label in labels)
            or len(set(labels)) != len(labels)
            or not isinstance(image_size, int) or not 32 <= image_size <= 1024):
        raise ValueError('Invalid checkpoint metadata')
    model = BanglaFoodNet(num_dishes=len(labels))
    model.load_state_dict(checkpoint['model_state_dict'], strict=True)
    device = torch.device(device_name)
    model.to(device).eval()
    transform = transforms.Compose([
        transforms.Resize((image_size, image_size)),
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
    ])
    with open(path, 'rb') as source:
        digest = sha256()
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(chunk)
    version = 'local:banglafoodnet:%s' % digest.hexdigest()[:16]
    return model, transform, tuple(labels), device, version


def local_candidates(image_bytes):
    configured = getattr(settings, 'AI_LOCAL_CHECKPOINT', '')
    if not configured:
        raise LocalModelError('MODEL_NOT_CONFIGURED', 'unavailable')
    path = Path(configured).expanduser()
    if not path.is_absolute():
        path = settings.BASE_DIR / path
    try:
        stat = path.stat()
    except (FileNotFoundError, NotADirectoryError):
        raise LocalModelError('MODEL_NOT_CONFIGURED', 'unavailable') from None
    except OSError:
        raise LocalModelError('LOCAL_MODEL_ERROR') from None
    try:
        # Serialize cold loads so concurrent uploads share one model per process.
        with _load_lock:
            model, transform, labels, device, version = _load_model(
                str(path.resolve()), stat.st_mtime_ns, stat.st_size, settings.AI_LOCAL_DEVICE)
        import torch
        with Image.open(BytesIO(image_bytes)) as image:
            tensor = transform(ImageOps.exif_transpose(image).convert('RGB')).unsqueeze(0).to(device)
        with torch.inference_mode():
            probabilities = model(tensor)['dish'].softmax(dim=1)[0]
            if probabilities.shape != (len(labels),) or not torch.isfinite(probabilities).all():
                raise ValueError('Invalid model output')
            scores, indices = probabilities.topk(min(5, len(labels)))
        candidates = [
            {'name': model_display_name(labels[index]), 'model_label': labels[index],
             'category': 'Dish', 'confidence': round(score, 3), 'food_id': None}
            for score, index in zip(scores.cpu().tolist(), indices.cpu().tolist())
        ]
        return candidates, version
    except ImportError:
        raise LocalModelError('LOCAL_DEPENDENCIES_MISSING', 'unavailable') from None
    except Exception:
        logger.exception('Local recognition failed')
        raise LocalModelError('LOCAL_MODEL_ERROR') from None


def recognize_locally(image_bytes):
    try:
        candidates, version = local_candidates(image_bytes)
    except LocalModelError as exc:
        return {'status': exc.status, 'candidates': [], 'model_version': '', 'error_code': exc.code}
    return {'status': 'completed', 'candidates': candidates, 'model_version': version, 'error_code': ''}
