"""Offline inference for the supplied DINOv3 dish classifier."""
from functools import lru_cache
from io import BytesIO
import logging
from pathlib import Path
from threading import Lock

from django.conf import settings
from PIL import Image, ImageOps, UnidentifiedImageError

from ml_models.inference.classifier import _load_cached_classifier, get_checkpoint_sha256_tag
from .recognition_labels import model_display_name

logger = logging.getLogger(__name__)
_load_lock = Lock()


def _model_dir():
    path = Path(settings.AI_DINOV3_MODEL_DIR).expanduser()
    return path if path.is_absolute() else settings.BASE_DIR / path


def _resolve_checkpoint_in_dir(root: Path) -> Path:
    ckpt = root / 'checkpoint.pth'
    if ckpt.is_file():
        return ckpt
    alt = settings.BASE_DIR.parent / 'ml_models' / 'classifier' / 'dinov3_dish_best.pth'
    if alt.is_file():
        return alt
    return ckpt


@lru_cache(maxsize=1)
def _load_model(directory, device_name):
    root = Path(directory)
    ckpt_path = _resolve_checkpoint_in_dir(root)
    return _load_cached_classifier(
        str(ckpt_path),
        str(root / 'backbone_config.json'),
        str(root / 'classes.json'),
        str(root / 'config.json'),
        device_name,
    )


def predict_food(image, top_k=None):
    """Return ranked uncalibrated softmax scores for one image."""
    import torch

    if top_k is None:
        top_k = settings.AI_DINOV3_TOP_K
    if isinstance(top_k, bool) or not isinstance(top_k, int) or not 1 <= top_k <= 9:
        raise ValueError('top_k must be an integer from 1 to 9')
    with _load_lock:
        model, transform, labels, device = _load_model(str(_model_dir().resolve()), settings.AI_DINOV3_DEVICE)
    if isinstance(image, (str, Path)):
        source = image
    elif isinstance(image, bytes):
        source = BytesIO(image)
    else:
        source = image
    try:
        with Image.open(source) as opened:
            if opened.format not in ('JPEG', 'PNG', 'WEBP') or opened.width * opened.height > 20_000_000:
                raise ValueError('Use a JPEG, PNG, or WebP under 20 megapixels')
            tensor = transform(ImageOps.exif_transpose(opened).convert('RGB')).unsqueeze(0).to(device)
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ValueError('Invalid image') from exc
    with torch.inference_mode():
        logits = model(tensor)[0]
        if logits.shape != (len(labels),) or not torch.isfinite(logits).all():
            raise ValueError('Invalid model output')
        scores, indices = logits.softmax(dim=0).topk(min(top_k, len(labels)))
    return [{'class_id': index, 'food_name': labels[index], 'confidence': float(score)}
            for score, index in zip(scores.cpu().tolist(), indices.cpu().tolist())]


def recognize_dinov3(image_bytes):
    try:
        predictions = predict_food(image_bytes)
    except (ImportError, ModuleNotFoundError):
        logger.exception('DINOv3 dependencies missing')
        return {'status': 'unavailable', 'candidates': [], 'model_version': '', 'error_code': 'LOCAL_DEPENDENCIES_MISSING'}
    except FileNotFoundError:
        logger.exception('DINOv3 artifact missing')
        return {'status': 'unavailable', 'candidates': [], 'model_version': '', 'error_code': 'MODEL_NOT_CONFIGURED'}
    except Exception:
        logger.exception('DINOv3 recognition failed')
        return {'status': 'failed', 'candidates': [], 'model_version': '', 'error_code': 'LOCAL_MODEL_ERROR'}
    ckpt_tag = get_checkpoint_sha256_tag(str(_resolve_checkpoint_in_dir(_model_dir().resolve())))
    model_version = f'local:dinov3:{ckpt_tag}' if ckpt_tag != 'untracked' else 'local:dinov3'
    return {'status': 'completed', 'model_version': model_version, 'error_code': '',
            'candidates': [{'name': model_display_name(item['food_name']), 'model_label': item['food_name'],
                            'category': 'Dish', 'confidence': round(item['confidence'], 3), 'food_id': None}
                           for item in predictions]}
