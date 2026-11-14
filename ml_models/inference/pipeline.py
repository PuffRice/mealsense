"""Complete Food Recognition & Nutrition Analysis Pipeline.

Coordinates:
1. Image validation and preprocessing
2. DINOv3 9-class food classification
3. Fine-tuned VLM ingredient & portion analysis
4. Grounded nutrition validation (FCTB 2013 + provenance)
5. Structured JSON validation for Django API & persistence
"""
from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

from PIL import Image

from .classifier import DINOv3FoodClassifier, open_and_validate_image
from .nutrition import NutritionValidationProvider
from .vlm import MealSenseVLMService, StructuredNutritionResponseSchema

logger = logging.getLogger(__name__)


def analyze_food_image(
    image: str | Path | bytes | Image.Image | Any,
    user: Any = None,
    *,
    checkpoint: str | None = None,
    device: str | None = None,
    top_k: int | None = None,
    run_vlm: bool = True,
    nutrition_provider: NutritionValidationProvider | None = None,
) -> dict[str, Any]:
    """Run the complete DINOv3 + Fine-Tuned VLM + Nutrition Validation pipeline on an image.

    Parameters
    ----------
    image:
        File path, raw bytes, file-like object, or PIL.Image.
    user:
        Optional authenticated Django User (used when linking catalog items or audit context).
    checkpoint:
        Optional VLM checkpoint alias ('mealsense-vlm-lora' or 'checkpoint-147').
    device:
        Optional device override ('auto', 'cuda', or 'cpu').
    top_k:
        Number of top DINOv3 classification candidates to return (1-9).
    run_vlm:
        If True (default), runs the fine-tuned VLM for ingredient & nutrition analysis on the top class.
    nutrition_provider:
        Optional custom NutritionValidationProvider instance.

    Returns
    -------
    dict
        Validated structured JSON containing classification, portion, ingredients,
        nutrition, micronutrients, confidence, provenance, warnings, and timing metrics.
    """
    t0 = time.perf_counter()
    rgb_image = open_and_validate_image(image)

    # Step 1: DINOv3 Classification
    t_cls_start = time.perf_counter()
    classifier = DINOv3FoodClassifier(device=device, top_k=top_k)
    cls_result = classifier.classify(rgb_image, top_k=top_k)
    t_cls_elapsed = time.perf_counter() - t_cls_start

    predicted_label = cls_result["predicted_food"]
    confidence = cls_result["confidence"]

    if not run_vlm:
        return {
            "food_name": predicted_label,
            "classification": {
                "predicted_label": predicted_label,
                "confidence": confidence,
                "top_predictions": cls_result["top_predictions"],
            },
            "portion": None,
            "ingredients": [],
            "nutrition": None,
            "micronutrients": None,
            "confidence": {
                "food_identification": confidence,
                "portion_estimation": None,
                "nutrition_estimation": None,
            },
            "warnings": (
                ["Low classification confidence; please confirm food identity."]
                if cls_result["requires_confirmation"]
                else []
            ),
            "explanation": "DINOv3 classification only (VLM analysis skipped).",
            "timing": {
                "classifier_seconds": round(t_cls_elapsed, 4),
                "vlm_seconds": 0.0,
                "total_seconds": round(time.perf_counter() - t0, 4),
            },
        }

    # Step 2: Fine-Tuned VLM + Nutrition Validation
    t_vlm_start = time.perf_counter()
    vlm_service = MealSenseVLMService(
        checkpoint=checkpoint,
        device=device,
        nutrition_provider=nutrition_provider,
    )
    analysis = vlm_service.analyze(
        image=rgb_image,
        predicted_label=predicted_label,
        confidence=confidence,
    )
    t_vlm_elapsed = time.perf_counter() - t_vlm_start

    # Validate final payload against schema
    StructuredNutritionResponseSchema.model_validate(analysis)

    # Enrich classification block with top_predictions from DINOv3
    analysis["classification"]["top_predictions"] = cls_result["top_predictions"]
    analysis["classification"]["ranked_classes"] = cls_result["ranked_classes"]
    analysis["timing"] = {
        "classifier_seconds": round(t_cls_elapsed, 4),
        "vlm_seconds": round(t_vlm_elapsed, 4),
        "total_seconds": round(time.perf_counter() - t0, 4),
    }
    if user is not None and getattr(user, "is_authenticated", False):
        analysis["user_id"] = str(getattr(user, "id", ""))

    return analysis
