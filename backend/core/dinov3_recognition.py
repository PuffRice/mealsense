"""Offline inference for the supplied DINOv3 dish classifier."""
from functools import lru_cache
from io import BytesIO
import json
import logging
from pathlib import Path
from threading import Lock

from django.conf import settings
from PIL import Image, ImageOps, UnidentifiedImageError

from .recognition_labels import model_display_name

logger = logging.getLogger(__name__)
_load_lock = Lock()


def _model_dir():
    path = Path(settings.AI_DINOV3_MODEL_DIR).expanduser()
    return path if path.is_absolute() else settings.BASE_DIR / path


@lru_cache(maxsize=1)
def _load_model(directory, device_name):
    import torch
    from torch import nn
    from torchvision import transforms
    from transformers import AutoConfig, AutoModel

    root = Path(directory)
    with (root / 'classes.json').open(encoding='utf-8') as source:
        labels = json.load(source)
    with (root / 'config.json').open(encoding='utf-8') as source:
        inference_config = json.load(source)
    if (not isinstance(labels, list) or not labels or len(set(labels)) != len(labels)
            or any(not isinstance(label, str) or not label.strip() for label in labels)
            or inference_config.get('image_size') != 224):
        raise ValueError('Invalid DINOv3 deployment metadata')
    checkpoint = torch.load(root / 'checkpoint.pth', map_location='cpu', weights_only=True)
    if checkpoint['dish_to_idx'] != {label: index for index, label in enumerate(labels)}:
        raise ValueError('Checkpoint class mapping differs from deployment mapping')
    if checkpoint['image_size'] != inference_config['image_size']:
        raise ValueError('Checkpoint image size differs from deployment config')

    backbone_config = AutoConfig.from_pretrained(str(root / 'backbone_config.json'), local_files_only=True)
    backbone = AutoModel.from_config(backbone_config)

    class DINOClassifier(nn.Module):
        def __init__(self):
            super().__init__()
            self.backbone = backbone
            self.head = nn.Sequential(nn.LayerNorm(backbone.config.hidden_size),
                                      nn.Dropout(0.25), nn.Linear(backbone.config.hidden_size, len(labels)))

        def forward(self, pixel_values):
            return self.head(self.backbone(pixel_values=pixel_values).last_hidden_state[:, 0])

    model = DINOClassifier()
    model.load_state_dict(checkpoint['state_dict'], strict=True)
    if device_name == 'auto':
        device_name = 'cuda' if torch.cuda.is_available() else 'cpu'
    if device_name not in ('cpu', 'cuda') or (device_name == 'cuda' and not torch.cuda.is_available()):
        raise ValueError('Requested inference device is unavailable')
    device = torch.device(device_name)
    model.to(device).eval()
    transform = transforms.Compose([
        transforms.Resize((224, 224)), transforms.ToTensor(),
        transforms.Normalize(inference_config['normalization_mean'], inference_config['normalization_std']),
    ])
    return model, transform, tuple(labels), device


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
    return {'status': 'completed', 'model_version': 'local:dinov3', 'error_code': '',
            'candidates': [{'name': model_display_name(item['food_name']), 'model_label': item['food_name'],
                            'category': 'Dish', 'confidence': round(item['confidence'], 3), 'food_id': None}
                           for item in predictions]}
