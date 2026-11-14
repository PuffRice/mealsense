"""Configuration loader and path resolution for MealSense ML models."""
from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
import os
from pathlib import Path
from typing import Any

import yaml

# Workspace root: d:/CS/Hackathon/mealsense
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
ML_MODELS_DIR = PROJECT_ROOT / "ml_models"
DEFAULT_CONFIG_PATH = ML_MODELS_DIR / "configs" / "model_config.yaml"


def resolve_project_path(raw_path: str | Path) -> Path:
    """Resolve a path relative to PROJECT_ROOT if not already absolute."""
    path = Path(raw_path).expanduser()
    if path.is_absolute():
        return path
    candidate = (PROJECT_ROOT / path).resolve()
    if candidate.exists():
        return candidate
    backend_candidate = (PROJECT_ROOT / "backend" / path).resolve()
    if backend_candidate.exists():
        return backend_candidate
    return candidate


@dataclass(frozen=True, slots=True)
class ClassifierConfig:
    architecture: str = "dinov3_vit"
    checkpoint_path: Path = ML_MODELS_DIR / "classifier" / "dinov3_dish_best.pth"
    fallback_checkpoint_path: Path = PROJECT_ROOT / "backend" / "ml_models" / "dinov3" / "checkpoint.pth"
    backbone_config_path: Path = ML_MODELS_DIR / "classifier" / "backbone_config.json"
    classes_path: Path = ML_MODELS_DIR / "classifier" / "classes.json"
    config_path: Path = ML_MODELS_DIR / "classifier" / "config.json"
    image_size: int = 224
    normalization_mean: tuple[float, float, float] = (0.485, 0.456, 0.406)
    normalization_std: tuple[float, float, float] = (0.229, 0.224, 0.225)
    top_k: int = 5
    confidence_threshold: float = 0.35
    confirmation_threshold: float = 0.65
    device: str = "auto"


@dataclass(frozen=True, slots=True)
class VLMCheckpointSpec:
    name: str
    adapter_path: Path
    processor_fallback_path: Path | None
    base_model_id: str
    local_base_model_dir: Path | None
    architecture: str
    processor_class: str
    use_peft: bool = True


@dataclass(frozen=True, slots=True)
class VLMConfig:
    selected_checkpoint: str = "mealsense-vlm-lora"
    checkpoints_root: Path = ML_MODELS_DIR / "checkpoints"
    checkpoints: dict[str, VLMCheckpointSpec] = field(default_factory=dict)
    device: str = "auto"
    dtype: str = "auto"
    quantization_enabled: bool = False
    load_in_4bit: bool = False
    bnb_4bit_quant_type: str = "nf4"
    bnb_4bit_use_double_quant: bool = True
    cpu_offload: bool = False
    image_size: int = 384
    enable_image_splitting: bool = False
    max_image_pixels: int = 20_000_000
    max_file_size_bytes: int = 8 * 1024 * 1024
    allowed_formats: tuple[str, ...] = ("JPEG", "PNG", "WEBP")
    max_new_tokens: int = 256
    do_sample: bool = False
    use_cache: bool = True

    def get_checkpoint_spec(self, checkpoint_name: str | None = None) -> VLMCheckpointSpec:
        target = (
            checkpoint_name
            or os.environ.get("MEALSENSE_VLM_CHECKPOINT")
            or self.selected_checkpoint
        ).strip()
        if target in self.checkpoints:
            return self.checkpoints[target]
        # Allow passing a direct path or relative directory inside checkpoints_root
        direct_path = resolve_project_path(target)
        if direct_path.is_dir():
            return VLMCheckpointSpec(
                name=direct_path.name,
                adapter_path=direct_path,
                processor_fallback_path=direct_path.parent if (direct_path.parent / "processor_config.json").exists() else None,
                base_model_id=os.environ.get("MEALSENSE_VLM_BASE_MODEL", "HuggingFaceTB/SmolVLM-500M-Instruct"),
                local_base_model_dir=resolve_project_path(
                    os.environ.get(
                        "MEALSENSE_VLM_LOCAL_BASE_DIR",
                        "../Mealsense_Models/mealsense_local_artifacts/SmolVLM-500M-Instruct",
                    )
                ),
                architecture="AutoModelForImageTextToText",
                processor_class="AutoProcessor",
                use_peft=True,
            )
        raise ValueError(
            f"Unknown VLM checkpoint '{target}'. Available configured checkpoints: {list(self.checkpoints.keys())}"
        )


@dataclass(frozen=True, slots=True)
class NutritionProviderConfig:
    provider: str = "fctb_2013"
    sqlite_db_path: Path = PROJECT_ROOT.parent / "Mealsense_Models" / "mealsense_local_artifacts" / "fctb_2013_nutrition.db"
    allow_remote_fallback: bool = False


@dataclass(frozen=True, slots=True)
class MealSenseMLConfig:
    classifier: ClassifierConfig
    vlm: VLMConfig
    nutrition: NutritionProviderConfig


@lru_cache(maxsize=4)
def load_ml_config(config_path: str | Path | None = None) -> MealSenseMLConfig:
    """Load and validate model_config.yaml with environment variable overrides."""
    path = resolve_project_path(
        config_path
        or os.environ.get("MEALSENSE_MODEL_CONFIG")
        or DEFAULT_CONFIG_PATH
    )
    raw: dict[str, Any] = {}
    if path.is_file():
        with path.open("r", encoding="utf-8") as fh:
            loaded = yaml.safe_load(fh)
            if isinstance(loaded, dict):
                raw = loaded

    cls_raw = raw.get("classifier", {}) or {}
    cls_ckpt = os.environ.get("MEALSENSE_CLASSIFIER_CHECKPOINT") or cls_raw.get(
        "checkpoint_path", "ml_models/classifier/dinov3_dish_best.pth"
    )
    cls_device = os.environ.get("AI_DINOV3_DEVICE") or os.environ.get("MEALSENSE_DEVICE") or cls_raw.get("device", "auto")
    classifier_cfg = ClassifierConfig(
        architecture=str(cls_raw.get("architecture", "dinov3_vit")),
        checkpoint_path=resolve_project_path(cls_ckpt),
        fallback_checkpoint_path=resolve_project_path(
            cls_raw.get("fallback_checkpoint_path", "backend/ml_models/dinov3/checkpoint.pth")
        ),
        backbone_config_path=resolve_project_path(
            cls_raw.get("backbone_config_path", "ml_models/classifier/backbone_config.json")
        ),
        classes_path=resolve_project_path(
            cls_raw.get("classes_path", "ml_models/classifier/classes.json")
        ),
        config_path=resolve_project_path(
            cls_raw.get("config_path", "ml_models/classifier/config.json")
        ),
        image_size=int(cls_raw.get("image_size", 224)),
        normalization_mean=tuple(float(x) for x in cls_raw.get("normalization_mean", [0.485, 0.456, 0.406])),
        normalization_std=tuple(float(x) for x in cls_raw.get("normalization_std", [0.229, 0.224, 0.225])),
        top_k=int(os.environ.get("AI_DINOV3_TOP_K", cls_raw.get("top_k", 5))),
        confidence_threshold=float(cls_raw.get("confidence_threshold", 0.35)),
        confirmation_threshold=float(cls_raw.get("confirmation_threshold", 0.65)),
        device=str(cls_device).strip().lower(),
    )

    vlm_raw = raw.get("vlm", {}) or {}
    ckpts_raw = vlm_raw.get("checkpoints", {}) or {}
    checkpoints: dict[str, VLMCheckpointSpec] = {}
    for name, spec in ckpts_raw.items():
        if not isinstance(spec, dict):
            continue
        fallback_proc = spec.get("processor_fallback_path")
        local_base = os.environ.get("MEALSENSE_VLM_LOCAL_BASE_DIR") or spec.get("local_base_model_dir")
        checkpoints[name] = VLMCheckpointSpec(
            name=name,
            adapter_path=resolve_project_path(spec.get("adapter_path", f"ml_models/checkpoints/{name}")),
            processor_fallback_path=resolve_project_path(fallback_proc) if fallback_proc else None,
            base_model_id=str(os.environ.get("MEALSENSE_VLM_BASE_MODEL") or spec.get("base_model_id", "HuggingFaceTB/SmolVLM-500M-Instruct")),
            local_base_model_dir=resolve_project_path(local_base) if local_base else None,
            architecture=str(spec.get("architecture", "Idefics3ForConditionalGeneration")),
            processor_class=str(spec.get("processor_class", "Idefics3Processor")),
            use_peft=bool(spec.get("use_peft", True)),
        )

    quant_raw = vlm_raw.get("quantization", {}) or {}
    img_raw = vlm_raw.get("image_processing", {}) or {}
    gen_raw = vlm_raw.get("generation", {}) or {}
    vlm_device = os.environ.get("MEALSENSE_VLM_DEVICE") or os.environ.get("MEALSENSE_DEVICE") or vlm_raw.get("device", "auto")
    selected_ckpt = os.environ.get("MEALSENSE_VLM_CHECKPOINT") or vlm_raw.get("selected_checkpoint", "mealsense-vlm-lora")
    quant_env = os.environ.get("MEALSENSE_VLM_LOAD_IN_4BIT", "").strip().lower()
    load_4bit = quant_env in ("1", "true", "yes") if quant_env else bool(quant_raw.get("load_in_4bit", False))

    vlm_cfg = VLMConfig(
        selected_checkpoint=str(selected_ckpt),
        checkpoints_root=resolve_project_path(vlm_raw.get("checkpoints_root", "ml_models/checkpoints")),
        checkpoints=checkpoints,
        device=str(vlm_device).strip().lower(),
        dtype=str(vlm_raw.get("dtype", "auto")),
        quantization_enabled=bool(quant_raw.get("enabled", False)) or load_4bit,
        load_in_4bit=load_4bit,
        bnb_4bit_quant_type=str(quant_raw.get("bnb_4bit_quant_type", "nf4")),
        bnb_4bit_use_double_quant=bool(quant_raw.get("bnb_4bit_use_double_quant", True)),
        cpu_offload=bool(quant_raw.get("cpu_offload", False)),
        image_size=int(img_raw.get("image_size", 384)),
        enable_image_splitting=bool(img_raw.get("enable_image_splitting", False)),
        max_image_pixels=int(img_raw.get("max_image_pixels", 20_000_000)),
        max_file_size_bytes=int(img_raw.get("max_file_size_bytes", 8 * 1024 * 1024)),
        allowed_formats=tuple(str(fmt).upper() for fmt in img_raw.get("allowed_formats", ["JPEG", "PNG", "WEBP"])),
        max_new_tokens=int(gen_raw.get("max_new_tokens", 256)),
        do_sample=bool(gen_raw.get("do_sample", False)),
        use_cache=bool(gen_raw.get("use_cache", True)),
    )

    nutr_raw = raw.get("nutrition", {}) or {}
    nutr_provider = os.environ.get("MEALSENSE_NUTRITION_PROVIDER") or nutr_raw.get("provider", "fctb_2013")
    nutr_db = os.environ.get("MEALSENSE_NUTRITION_DB_PATH") or nutr_raw.get(
        "sqlite_db_path", "../Mealsense_Models/mealsense_local_artifacts/fctb_2013_nutrition.db"
    )
    nutrition_cfg = NutritionProviderConfig(
        provider=str(nutr_provider).strip().lower(),
        sqlite_db_path=resolve_project_path(nutr_db),
        allow_remote_fallback=bool(nutr_raw.get("allow_remote_fallback", False)),
    )

    return MealSenseMLConfig(
        classifier=classifier_cfg,
        vlm=vlm_cfg,
        nutrition=nutrition_cfg,
    )
