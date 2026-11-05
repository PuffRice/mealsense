"""Vision-based Food vs. Non-Food image classifier and dataset filter."""

from __future__ import annotations

import json
import logging
import os
import shutil
import warnings
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd
from PIL import Image
from tqdm import tqdm

# Suppress Hugging Face Hub symlink warnings on Windows
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
warnings.filterwarnings("ignore", message=".*symlinks by default.*")

logger = logging.getLogger(__name__)

DEFAULT_FOOD_MODEL_ID = "wkcn/TinyCLIP-ViT-8M-16-Text-3M-YFCC15M"

FOOD_CANDIDATE_LABELS = [
    "a photo of delicious food, a meal, cooked dish, snacks, or dessert",
    "a close-up photo of pizza, biryani, fried rice, noodles, meat, cake, or drinks on a table",
    "a graphic poster with text, flyer, meme, or promotional banner without real food",
    "a mobile phone screenshot, price menu card, or text announcement",
    "a photo of a person, selfie, building, trees, sky, or beach without food",
    "a closed plastic packet or wrapper held in hand without open food",
]


@dataclass
class FoodClassificationResult:
    """Classification output for a single image file."""

    filename: str
    is_food: bool
    food_confidence: float
    text_poster_confidence: float
    other_non_food_confidence: float
    predicted_label: str
    destination_path: str

    def to_dict(self) -> Dict[str, object]:
        """Return a JSON/CSV serializable dictionary."""
        return asdict(self)


class FoodImageClassifier:
    """Classifies images as Food vs. Non-Food using a downloadable Hugging Face CLIP vision model.

    Supports automatic hardware acceleration on:
    - Apple Silicon macOS via Metal Performance Shaders (MPS)
    - NVIDIA GPUs via CUDA
    - CPU fallback
    """

    def __init__(
        self,
        model_id: str = DEFAULT_FOOD_MODEL_ID,
        confidence_threshold: float = 0.50,
        device: str = "auto",
    ) -> None:
        self.model_id = model_id
        self.confidence_threshold = confidence_threshold
        self.requested_device = device
        self.device = None
        self._model = None
        self._processor = None

    def _resolve_device(self, torch_module) -> str:
        """Resolve the target execution device ('cpu', 'cuda', 'mps')."""
        req = (self.requested_device or "auto").strip().lower()
        if req in ("cuda", "mps", "cpu"):
            if req == "cuda" and not torch_module.cuda.is_available():
                logger.warning("CUDA requested but not available; using CPU instead.")
                return "cpu"
            if req == "mps" and not (
                hasattr(torch_module.backends, "mps")
                and torch_module.backends.mps.is_available()
            ):
                logger.warning("MPS requested but not available on this system; using CPU instead.")
                return "cpu"
            return req

        # Automatic detection: CUDA > Apple Silicon MPS > CPU
        if torch_module.cuda.is_available():
            return "cuda"
        if hasattr(torch_module.backends, "mps") and torch_module.backends.mps.is_available():
            return "mps"
        return "cpu"

    def _ensure_loaded(self) -> None:
        """Lazily load the Hugging Face CLIP model and processor on the optimal device."""
        if self._model is not None and self._processor is not None:
            return

        import torch
        from transformers import CLIPModel, CLIPProcessor

        resolved_device_str = self._resolve_device(torch)
        self.device = torch.device(resolved_device_str)
        logger.info(
            "Loading downloadable vision model '%s' on %s (MPS/CUDA/CPU)...",
            self.model_id,
            self.device,
        )
        self._processor = CLIPProcessor.from_pretrained(self.model_id)
        self._model = CLIPModel.from_pretrained(self.model_id)
        self._model.to(self.device)
        self._model.eval()
        self._torch = torch

    def classify_image(self, image_path: Path) -> tuple[bool, float, float, float]:
        """Classify an image file and return `(is_food, food_prob, poster_prob, other_prob)`."""
        self._ensure_loaded()

        with Image.open(image_path) as raw_img:
            img = raw_img.convert("RGB")

        inputs = self._processor(
            text=FOOD_CANDIDATE_LABELS,
            images=img,
            return_tensors="pt",
            padding=True,
        )
        if self.device is not None and self.device.type != "cpu":
            inputs = {
                k: v.to(self.device) if hasattr(v, "to") else v
                for k, v in inputs.items()
            }

        try:
            with self._torch.no_grad():
                outputs = self._model(**inputs)
                probs = outputs.logits_per_image.softmax(dim=1)[0].tolist()
        except Exception as exc:
            # Graceful fallback to CPU if accelerated device (MPS/CUDA) encounters an op error
            if self.device is not None and self.device.type != "cpu":
                logger.warning(
                    "Inference failed on %s device (%s); falling back to CPU.",
                    self.device,
                    exc,
                )
                self.device = self._torch.device("cpu")
                self._model.to(self.device)
                inputs = {
                    k: v.to(self.device) if hasattr(v, "to") else v
                    for k, v in inputs.items()
                }
                with self._torch.no_grad():
                    outputs = self._model(**inputs)
                    probs = outputs.logits_per_image.softmax(dim=1)[0].tolist()
            else:
                raise

        if len(probs) >= 6:
            food_prob = float(probs[0] + probs[1])
            poster_prob = float(probs[2] + probs[3])
            other_prob = float(probs[4] + probs[5])
        else:
            food_prob = float(probs[0])
            poster_prob = float(probs[1]) if len(probs) > 1 else 0.0
            other_prob = float(probs[2]) if len(probs) > 2 else 0.0
        is_food = food_prob >= self.confidence_threshold
        return is_food, round(food_prob, 4), round(poster_prob, 4), round(other_prob, 4)


def filter_and_move_food_images(
    dataset_dir: Path,
    food_dir_name: str = "food_images",
    non_food_dir_name: Optional[str] = "non_food_images",
    confidence_threshold: float = 0.50,
    device: str = "auto",
    classifier: Optional[FoodImageClassifier] = None,
    show_progress: bool = True,
) -> Dict[str, object]:
    """Filter images in `<dataset_dir>` and move food images into `<dataset_dir>/<food_dir_name>`.

    Non-food images are moved into `<dataset_dir>/<non_food_dir_name>` (or kept in `images/` if
    `non_food_dir_name=None`) so that `<dataset_dir>/<food_dir_name>` contains exclusively
    verified food images.

    When `images/` has already been moved by a previous run into `food_images/` and
    `non_food_images/`, this function automatically scans all three directories so re-running
    `--filter-only` (e.g. with a new `--food-threshold`) always evaluates the full dataset
    instead of reporting 0 evaluated images.

    Also writes:
    - `<dataset_dir>/metadata/food_images_metadata.csv`
    - `<dataset_dir>/metadata/food_images_metadata.json`
    - `<dataset_dir>/metadata/food_classification_report.json`
    """
    images_dir = dataset_dir / "images"
    food_dir = dataset_dir / food_dir_name
    non_food_dir = (dataset_dir / non_food_dir_name) if non_food_dir_name else None
    metadata_dir = dataset_dir / "metadata"

    food_dir.mkdir(parents=True, exist_ok=True)
    if non_food_dir is not None:
        non_food_dir.mkdir(parents=True, exist_ok=True)
    metadata_dir.mkdir(parents=True, exist_ok=True)

    image_extensions = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tiff"}

    # Collect candidate image files across images/, food_dir, and non_food_dir so re-runs
    # always evaluate all dataset images even after they were moved out of images/.
    # Note: On macOS, hidden files (.DS_Store) and AppleDouble files (._*) are ignored.
    candidate_map: Dict[str, Path] = {}
    search_dirs = [images_dir, food_dir]
    if non_food_dir is not None:
        search_dirs.append(non_food_dir)

    for folder in search_dirs:
        if folder.exists():
            for f in sorted(folder.iterdir()):
                if (
                    f.is_file()
                    and not f.name.startswith(".")
                    and f.suffix.lower() in image_extensions
                ):
                    if f.name not in candidate_map:
                        candidate_map[f.name] = f

    source_files: List[Path] = [candidate_map[name] for name in sorted(candidate_map.keys())]

    model_classifier = classifier or FoodImageClassifier(
        confidence_threshold=confidence_threshold,
        device=device,
    )

    results: List[FoodClassificationResult] = []
    food_filenames: set[str] = set()
    food_count = 0
    non_food_count = 0

    iterator = (
        tqdm(source_files, desc="Filtering food images", unit="img")
        if show_progress and source_files
        else source_files
    )

    for img_path in iterator:
        try:
            is_food, food_prob, poster_prob, other_prob = model_classifier.classify_image(img_path)
        except Exception as exc:
            logger.warning("Failed to classify image %s: %s", img_path, exc)
            continue

        if is_food:
            dest_path = food_dir / img_path.name
            if img_path.resolve() != dest_path.resolve():
                shutil.move(str(img_path), str(dest_path))
            food_count += 1
            food_filenames.add(img_path.name)
            label = "food"
        else:
            if non_food_dir is not None:
                dest_path = non_food_dir / img_path.name
                if img_path.resolve() != dest_path.resolve():
                    shutil.move(str(img_path), str(dest_path))
            else:
                dest_path = images_dir / img_path.name
                if img_path.resolve() != dest_path.resolve():
                    images_dir.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(img_path), str(dest_path))
            non_food_count += 1
            label = "text_poster" if poster_prob >= other_prob else "non_food_object"

        results.append(
            FoodClassificationResult(
                filename=img_path.name,
                is_food=is_food,
                food_confidence=food_prob,
                text_poster_confidence=poster_prob,
                other_non_food_confidence=other_prob,
                predicted_label=label,
                destination_path=str(dest_path.relative_to(dataset_dir)),
            )
        )

    # Also include any images that were already moved to food_dir in an earlier run
    for existing_food in sorted(food_dir.iterdir()):
        if (
            existing_food.is_file()
            and not existing_food.name.startswith(".")
            and existing_food.suffix.lower() in image_extensions
        ):
            food_filenames.add(existing_food.name)

    # Filter the main metadata CSV/JSON to produce food_images_metadata.csv and .json
    main_csv_path = metadata_dir / "images_metadata.csv"
    food_csv_path = metadata_dir / "food_images_metadata.csv"
    food_json_path = metadata_dir / "food_images_metadata.json"
    classification_csv_path = metadata_dir / "image_classifications.csv"
    report_path = metadata_dir / "food_classification_report.json"

    score_map = {r.filename: r for r in results}

    if results:
        pd.DataFrame([r.to_dict() for r in results]).to_csv(
            classification_csv_path, index=False, encoding="utf-8"
        )

    if main_csv_path.exists():
        try:
            df = pd.read_csv(main_csv_path)
            food_df = df[df["filename"].isin(food_filenames)].copy()
            food_df["food_confidence"] = food_df["filename"].map(
                lambda fn: score_map[fn].food_confidence if fn in score_map else 1.0
            )
            food_df["filtered_path"] = food_df["filename"].map(
                lambda fn: f"{food_dir_name}/{fn}"
            )
            food_df.to_csv(food_csv_path, index=False, encoding="utf-8")
            food_json_path.write_text(
                json.dumps(food_df.to_dict(orient="records"), indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception as exc:
            logger.warning("Could not write filtered food metadata: %s", exc)

    summary_report: Dict[str, object] = {
        "model_id": model_classifier.model_id,
        "device": str(model_classifier.device) if model_classifier.device else "uninitialized",
        "confidence_threshold": confidence_threshold,
        "dataset_directory": str(dataset_dir),
        "food_images_directory": str(food_dir),
        "non_food_images_directory": str(non_food_dir) if non_food_dir else str(images_dir),
        "total_images_evaluated_this_run": len(results),
        "food_images_moved_this_run": food_count,
        "non_food_images_filtered_out_this_run": non_food_count,
        "total_food_images_in_directory": len(food_filenames),
        "classifications": [r.to_dict() for r in results],
    }

    report_path.write_text(
        json.dumps(summary_report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return summary_report
