"""MealSense ML Inference package."""
from .classifier import (
    ClassifierError,
    DINOv3FoodClassifier,
    InvalidImageError,
    classify_food_image,
    clear_classifier_cache,
    open_and_validate_image,
)
from .config import load_ml_config, resolve_project_path
from .nutrition import (
    ALLOWED_FOOD_CLASSES,
    NINE_CLASS_KNOWLEDGE_BASE,
    NutritionValidationProvider,
    normalize_ingredient_key,
)
from .pipeline import analyze_food_image
from .vlm import (
    MealSenseVLMService,
    StructuredNutritionResponseSchema,
    VLMInferenceError,
    analyze_with_vlm,
    clear_vlm_cache,
    extract_json_object,
)

__all__ = [
    "ALLOWED_FOOD_CLASSES",
    "ClassifierError",
    "DINOv3FoodClassifier",
    "InvalidImageError",
    "MealSenseVLMService",
    "NINE_CLASS_KNOWLEDGE_BASE",
    "NutritionValidationProvider",
    "StructuredNutritionResponseSchema",
    "VLMInferenceError",
    "analyze_food_image",
    "analyze_with_vlm",
    "classify_food_image",
    "clear_classifier_cache",
    "clear_vlm_cache",
    "extract_json_object",
    "load_ml_config",
    "normalize_ingredient_key",
    "open_and_validate_image",
    "resolve_project_path",
]
