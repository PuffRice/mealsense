"""DINOv3 Dish Classifier Inference Module.

Reproduces the exact architecture and preprocessing from the training notebook:
- Frozen DINOv3 ViT small backbone (384 hidden size, 12 layers, 4 register tokens)
- Head: LayerNorm(384) -> Dropout(0.25) -> Linear(384, 9) using the CLS token
- Preprocessing: EXIF transpose -> RGB -> Resize(224, 224) -> ToTensor -> ImageNet Normalize
"""
from __future__ import annotations

from functools import lru_cache
import hashlib
from io import BytesIO
import json
import logging
from pathlib import Path
from threading import Lock
from typing import Any

from PIL import Image, ImageOps, UnidentifiedImageError

from .config import ClassifierConfig, load_ml_config, resolve_project_path

logger = logging.getLogger(__name__)
_classifier_lock = Lock()


@lru_cache(maxsize=8)
def get_checkpoint_sha256_tag(checkpoint_path: str) -> str:
    """Return a 16-char SHA-256 digest tag for a checkpoint artifact."""
    path = Path(checkpoint_path)
    if not path.is_file():
        return "untracked"
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()[:16]


class ClassifierError(RuntimeError):
    """Raised when DINOv3 classifier loading or inference fails."""


class InvalidImageError(ValueError):
    """Raised when an input image is corrupt, unsupported, or exceeds bounds."""


def _resolve_checkpoint_and_metadata(cfg: ClassifierConfig) -> tuple[Path, Path, Path, Path]:
    ckpt_path = cfg.checkpoint_path
    if not ckpt_path.is_file() and cfg.fallback_checkpoint_path.is_file():
        ckpt_path = cfg.fallback_checkpoint_path
    if not ckpt_path.is_file():
        raise FileNotFoundError(
            f"DINOv3 checkpoint not found at {cfg.checkpoint_path} or {cfg.fallback_checkpoint_path}"
        )

    fallback_dir = cfg.fallback_checkpoint_path.parent
    backbone_cfg = (
        cfg.backbone_config_path
        if cfg.backbone_config_path.is_file()
        else fallback_dir / "backbone_config.json"
    )
    classes_file = (
        cfg.classes_path
        if cfg.classes_path.is_file()
        else fallback_dir / "classes.json"
    )
    config_file = (
        cfg.config_path
        if cfg.config_path.is_file()
        else fallback_dir / "config.json"
    )
    if not backbone_cfg.is_file():
        raise FileNotFoundError(f"DINOv3 backbone_config.json not found at {backbone_cfg}")
    return ckpt_path, backbone_cfg, classes_file, config_file


@lru_cache(maxsize=2)
def _load_cached_classifier(
    checkpoint_path_str: str,
    backbone_config_str: str,
    classes_path_str: str,
    config_path_str: str,
    device_name: str,
):
    import torch
    from torch import nn
    from torchvision import transforms
    from transformers import AutoConfig, AutoModel

    ckpt_path = Path(checkpoint_path_str)
    backbone_cfg_path = Path(backbone_config_str)
    classes_path = Path(classes_path_str)
    config_path = Path(config_path_str)

    try:
        checkpoint = torch.load(ckpt_path, map_location="cpu", weights_only=True)
    except Exception as exc:
        raise ClassifierError(f"Failed to load DINOv3 checkpoint: {exc}") from exc

    if not isinstance(checkpoint, dict) or "state_dict" not in checkpoint or "dish_to_idx" not in checkpoint:
        raise ClassifierError("Invalid DINOv3 checkpoint structure; missing state_dict or dish_to_idx")

    dish_to_idx: dict[str, int] = checkpoint["dish_to_idx"]
    idx_to_dish = {int(idx): str(label) for label, idx in dish_to_idx.items()}
    labels = [idx_to_dish[i] for i in range(len(idx_to_dish))]

    if classes_path.is_file():
        with classes_path.open("r", encoding="utf-8") as fh:
            deployed_labels = json.load(fh)
        if deployed_labels != labels:
            raise ClassifierError("Checkpoint class mapping differs from classes.json")

    image_size = int(checkpoint.get("image_size", 224))
    mean = [0.485, 0.456, 0.406]
    std = [0.229, 0.224, 0.225]
    if config_path.is_file():
        with config_path.open("r", encoding="utf-8") as fh:
            inf_cfg = json.load(fh)
        if inf_cfg.get("image_size", 224) != image_size:
            raise ClassifierError("Checkpoint image_size differs from config.json")
        mean = inf_cfg.get("normalization_mean", mean)
        std = inf_cfg.get("normalization_std", std)

    backbone_config = AutoConfig.from_pretrained(str(backbone_cfg_path), local_files_only=True)
    backbone = AutoModel.from_config(backbone_config)

    class DINOClassifier(nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.backbone = backbone
            hidden_size = backbone.config.hidden_size
            self.head = nn.Sequential(
                nn.LayerNorm(hidden_size),
                nn.Dropout(0.25),
                nn.Linear(hidden_size, len(labels)),
            )

        def forward(self, pixel_values):
            features = self.backbone(pixel_values=pixel_values).last_hidden_state[:, 0]
            return self.head(features)

    model = DINOClassifier()
    try:
        model.load_state_dict(checkpoint["state_dict"], strict=True)
    except Exception as exc:
        raise ClassifierError(f"Incompatible DINOv3 state_dict weights: {exc}") from exc

    resolved_device = device_name.strip().lower()
    if resolved_device == "auto":
        resolved_device = "cuda" if torch.cuda.is_available() else "cpu"
    if resolved_device not in ("cpu", "cuda") or (resolved_device == "cuda" and not torch.cuda.is_available()):
        raise ClassifierError(f"Requested classifier device '{device_name}' is unavailable")

    device = torch.device(resolved_device)
    model.to(device).eval()

    transform = transforms.Compose([
        transforms.Resize((image_size, image_size)),
        transforms.ToTensor(),
        transforms.Normalize(mean, std),
    ])

    return model, transform, tuple(labels), device


def open_and_validate_image(
    image_input: str | Path | bytes | Image.Image | Any,
    max_pixels: int = 20_000_000,
    allowed_formats: tuple[str, ...] = ("JPEG", "PNG", "WEBP"),
) -> Image.Image:
    """Validate and open an uploaded food image into an EXIF-transposed RGB PIL Image."""
    if isinstance(image_input, Image.Image):
        if image_input.width * image_input.height > max_pixels:
            raise InvalidImageError("Image resolution exceeds 20 megapixels.")
        return ImageOps.exif_transpose(image_input).convert("RGB")

    if isinstance(image_input, (str, Path)):
        path = Path(image_input)
        if not path.is_file():
            raise FileNotFoundError(f"Image file not found: {path}")
        source: Any = path
    elif isinstance(image_input, (bytes, bytearray)):
        if not image_input:
            raise InvalidImageError("Empty image payload.")
        source = BytesIO(bytes(image_input))
    elif hasattr(image_input, "read"):
        if hasattr(image_input, "seek"):
            image_input.seek(0)
        raw_bytes = image_input.read()
        if hasattr(image_input, "seek"):
            image_input.seek(0)
        if not raw_bytes:
            raise InvalidImageError("Empty image file stream.")
        source = BytesIO(raw_bytes)
    else:
        raise InvalidImageError("Unsupported image input type.")

    try:
        with Image.open(source) as opened:
            fmt = (opened.format or "").upper()
            if fmt not in allowed_formats:
                raise InvalidImageError(
                    f"Unsupported image format '{fmt or 'UNKNOWN'}'. Allowed formats: {', '.join(allowed_formats)}."
                )
            if opened.width * opened.height > max_pixels:
                raise InvalidImageError("Image resolution exceeds maximum allowed dimensions (20 MP).")
            return ImageOps.exif_transpose(opened).convert("RGB")
    except InvalidImageError:
        raise
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise InvalidImageError("Corrupt or invalid image file.") from exc


class DINOv3FoodClassifier:
    """Service wrapper for DINOv3 dish classification."""

    def __init__(
        self,
        checkpoint_path: str | Path | None = None,
        device: str | None = None,
        top_k: int | None = None,
        confidence_threshold: float | None = None,
    ) -> None:
        base_cfg = load_ml_config().classifier
        self.cfg = ClassifierConfig(
            architecture=base_cfg.architecture,
            checkpoint_path=resolve_project_path(checkpoint_path) if checkpoint_path else base_cfg.checkpoint_path,
            fallback_checkpoint_path=base_cfg.fallback_checkpoint_path,
            backbone_config_path=base_cfg.backbone_config_path,
            classes_path=base_cfg.classes_path,
            config_path=base_cfg.config_path,
            image_size=base_cfg.image_size,
            normalization_mean=base_cfg.normalization_mean,
            normalization_std=base_cfg.normalization_std,
            top_k=top_k if top_k is not None else base_cfg.top_k,
            confidence_threshold=(
                confidence_threshold if confidence_threshold is not None else base_cfg.confidence_threshold
            ),
            confirmation_threshold=base_cfg.confirmation_threshold,
            device=device if device is not None else base_cfg.device,
        )

    def load(self):
        ckpt, backbone_cfg, classes_path, config_path = _resolve_checkpoint_and_metadata(self.cfg)
        with _classifier_lock:
            return _load_cached_classifier(
                str(ckpt.resolve()),
                str(backbone_cfg.resolve()),
                str(classes_path.resolve()),
                str(config_path.resolve()),
                self.cfg.device,
            )

    def classify(
        self,
        image: str | Path | bytes | Image.Image | Any,
        top_k: int | None = None,
    ) -> dict[str, Any]:
        """Run DINOv3 classification on an image and return structured top-k predictions."""
        import torch

        k = top_k if top_k is not None else self.cfg.top_k
        if isinstance(k, bool) or not isinstance(k, int) or not 1 <= k <= 9:
            raise ValueError("top_k must be an integer between 1 and 9.")

        rgb_image = open_and_validate_image(image)
        model, transform, labels, device = self.load()

        tensor = transform(rgb_image).unsqueeze(0).to(device)
        with torch.inference_mode():
            logits = model(tensor)[0]
            if logits.shape != (len(labels),) or not torch.isfinite(logits).all():
                raise ClassifierError("Invalid DINOv3 model output tensor.")
            probs = logits.softmax(dim=0)
            scores, indices = probs.topk(min(k, len(labels)))

        top_predictions = [
            {
                "label": labels[idx],
                "class_id": int(idx),
                "confidence": round(float(score), 4),
            }
            for score, idx in zip(scores.cpu().tolist(), indices.cpu().tolist())
        ]
        best = top_predictions[0]
        is_low_confidence = best["confidence"] < self.cfg.confidence_threshold
        requires_confirmation = best["confidence"] < self.cfg.confirmation_threshold
        ckpt, _, _, _ = _resolve_checkpoint_and_metadata(self.cfg)
        ckpt_tag = get_checkpoint_sha256_tag(str(ckpt.resolve()))

        return {
            "predicted_food": best["label"],
            "confidence": best["confidence"],
            "model_version": f"local:dinov3:{ckpt_tag}" if ckpt_tag != "untracked" else "local:dinov3",
            "is_low_confidence": is_low_confidence,
            "requires_confirmation": requires_confirmation,
            "top_predictions": [
                {"label": item["label"], "confidence": item["confidence"]}
                for item in top_predictions
            ],
            "ranked_classes": [
                {
                    "class_id": item["class_id"],
                    "food_name": item["label"],
                    "confidence": item["confidence"],
                }
                for item in top_predictions
            ],
            "device": str(device),
        }


def classify_food_image(
    image: str | Path | bytes | Image.Image | Any,
    top_k: int | None = None,
    device: str | None = None,
    checkpoint_path: str | Path | None = None,
) -> dict[str, Any]:
    """Convenience function to classify a single food image with DINOv3."""
    classifier = DINOv3FoodClassifier(
        checkpoint_path=checkpoint_path,
        device=device,
        top_k=top_k,
    )
    return classifier.classify(image, top_k=top_k)


def clear_classifier_cache() -> None:
    """Clear the cached DINOv3 model instance."""
    _load_cached_classifier.cache_clear()
