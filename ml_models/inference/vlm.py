"""Fine-Tuned Vision-Language Model (VLM) Inference Service.

Supports configurable LoRA adapters (SmolVLM-500M-Instruct / Idefics3 and
Qwen2.5-VL-3B-Instruct) with lazy loading, processor caching, bfloat16/4-bit
quantization, CPU fallback, and Pydantic v2 structured JSON validation.
"""
from __future__ import annotations

from contextlib import nullcontext
from functools import lru_cache
import json
import logging
from pathlib import Path
import re
from threading import Lock
from typing import Any, Literal

from PIL import Image
from pydantic import BaseModel, Field

from .classifier import open_and_validate_image
from .config import VLMCheckpointSpec, VLMConfig, load_ml_config, resolve_project_path
from .nutrition import (
    ALLOWED_FOOD_CLASSES,
    NINE_CLASS_KNOWLEDGE_BASE,
    NutritionValidationProvider,
)

logger = logging.getLogger(__name__)
_vlm_lock = Lock()


class VLMInferenceError(RuntimeError):
    """Raised when VLM model loading or generation fails."""


class VisibleIngredientSchema(BaseModel):
    name: str
    visual_confidence: float = Field(default=0.85, ge=0.0, le=1.0)
    estimated_volume_share: float = Field(default=0.0, ge=0.0, le=1.0)


class VLMVisionOutputSchema(BaseModel):
    dish_matches_prediction: bool = True
    visual_fullness_multiplier: float = Field(default=1.0, ge=0.25, le=3.0)
    portion_confidence: Literal["high", "medium", "low"] = "medium"
    visible_ingredients: list[VisibleIngredientSchema] = Field(default_factory=list)
    observed_preparation_state: str = ""
    occluded_or_uncertain: bool = False


class ClassificationSchema(BaseModel):
    predicted_label: str
    confidence: float = Field(ge=0.0, le=1.0)


class PortionSchema(BaseModel):
    estimated_weight_g: float | None = Field(default=None, gt=0.0)
    portion_description: str
    weight_range_g: list[float] | None = None
    fullness_multiplier: float | None = None
    is_approximate: bool = True


class IngredientItemSchema(BaseModel):
    name: str
    estimated_weight_g: float = Field(ge=0.0)
    ingredient_key: str | None = None
    identification: Literal["visible", "recipe_inferred"] | None = None
    confidence: float | None = None
    nutrition_source: str | None = None
    recipe_source: str | None = None
    calories_kcal: float | None = None
    protein_g: float | None = None
    carbohydrates_g: float | None = None
    fat_g: float | None = None


class NutritionBlockSchema(BaseModel):
    calories_kcal: float | None = None
    protein_g: float | None = None
    carbohydrates_g: float | None = None
    fat_g: float | None = None
    fiber_g: float | None = None


class MicronutrientsBlockSchema(BaseModel):
    iron_mg: float | None = None
    calcium_mg: float | None = None
    potassium_mg: float | None = None


class ConfidenceBreakdownSchema(BaseModel):
    food_identification: float = Field(ge=0.0, le=1.0)
    portion_estimation: float | None = Field(default=None, ge=0.0, le=1.0)
    nutrition_estimation: float | None = Field(default=None, ge=0.0, le=1.0)


class StructuredNutritionResponseSchema(BaseModel):
    food_name: str
    canonical_catalog_name: str | None = None
    food_class: str | None = None
    classification: ClassificationSchema
    portion: PortionSchema
    ingredients: list[IngredientItemSchema]
    nutrition: NutritionBlockSchema
    micronutrients: MicronutrientsBlockSchema
    confidence: ConfidenceBreakdownSchema
    provenance: dict[str, Any] = Field(default_factory=dict)
    observed_preparation_state: str | None = None
    occluded_or_uncertain: bool = False
    requires_user_confirmation: bool = True
    warnings: list[str] = Field(default_factory=list)
    explanation: str


SYSTEM_PROMPT = (
    "You are the MealSense Bangladeshi culinary vision analyzer restricted strictly to 9 classes: "
    f"{', '.join(ALLOWED_FOOD_CLASSES)}. "
    "Given the image, DINOv3 prediction, and candidate ingredients, output strict JSON with visible "
    "ingredients and portion fullness. Never mark hidden oil or spices as visible."
)


def build_vlm_user_prompt(food_class: str, confidence: float, candidates: list[str]) -> str:
    """Build the exact prompt used during LoRA fine-tuning."""
    return (
        f"{SYSTEM_PROMPT}\n"
        f"DINOv3 Class: {food_class} (confidence: {confidence:.2f})\n"
        f"Candidate Ingredients: {', '.join(candidates)}\n"
        "Extract visible ingredients and portion metadata as strict JSON."
    )


def extract_json_object(raw_text: str) -> dict[str, Any]:
    """Safely extract and parse a JSON object from model output without trusting raw strings."""
    if not raw_text or not isinstance(raw_text, str):
        return {}
    cleaned = re.sub(r"```(?:json)?\s*|```", "", raw_text).strip()
    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
    if match:
        candidate = match.group(0)
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            # Attempt lightweight repair of trailing commas or truncated braces
            repaired = re.sub(r",\s*([}\]])", r"\1", candidate)
            try:
                parsed = json.loads(repaired)
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                pass
    return {}


def _resolve_base_model_source(spec: VLMCheckpointSpec, adapter_cfg: dict[str, Any]) -> str:
    """Resolve the local base model directory or Hugging Face repo ID."""
    # 1. Check explicit local_base_model_dir from config
    if spec.local_base_model_dir and (spec.local_base_model_dir / "config.json").is_file():
        return str(spec.local_base_model_dir.resolve())

    # 2. Check HF snapshot cache inside local_base_model_dir (e.g., models--Qwen--Qwen2.5-VL-3B-Instruct/snapshots/*)
    if spec.local_base_model_dir and (spec.local_base_model_dir / "snapshots").is_dir():
        snapshots = sorted((spec.local_base_model_dir / "snapshots").iterdir())
        for snap in reversed(snapshots):
            if (snap / "config.json").is_file():
                return str(snap.resolve())

    # 3. Check base_model_name_or_path recorded in adapter_config.json
    recorded_base = adapter_cfg.get("base_model_name_or_path")
    if recorded_base:
        rec_path = resolve_project_path(recorded_base)
        if (rec_path / "config.json").is_file():
            return str(rec_path.resolve())

    # 4. Fall back to Hugging Face repo ID
    return spec.base_model_id


def _resolve_processor_source(spec: VLMCheckpointSpec, base_source: str) -> str:
    """Resolve the directory containing processor/tokenizer configuration files."""
    for candidate in (spec.adapter_path, spec.processor_fallback_path):
        if candidate and candidate.is_dir():
            has_proc = (
                (candidate / "processor_config.json").is_file()
                or (candidate / "preprocessor_config.json").is_file()
            )
            has_tok = (candidate / "tokenizer_config.json").is_file()
            if has_proc and has_tok:
                return str(candidate.resolve())
    return base_source


@lru_cache(maxsize=2)
def _load_cached_vlm(
    checkpoint_name: str,
    adapter_path_str: str,
    processor_source: str,
    base_source: str,
    device_preference: str,
    dtype_preference: str,
    load_in_4bit: bool,
    cpu_offload: bool,
    image_size: int,
    enable_image_splitting: bool,
):
    import torch
    from peft import PeftModel
    from transformers import AutoModelForImageTextToText, AutoProcessor, BitsAndBytesConfig

    adapter_dir = Path(adapter_path_str)
    if not adapter_dir.is_dir():
        raise FileNotFoundError(f"VLM checkpoint directory does not exist: {adapter_dir}")

    adapter_cfg_file = adapter_dir / "adapter_config.json"
    full_cfg_file = adapter_dir / "config.json"
    if not adapter_cfg_file.is_file() and not full_cfg_file.is_file():
        raise FileNotFoundError(
            f"VLM checkpoint '{checkpoint_name}' at {adapter_dir} is empty or missing adapter_config.json."
        )

    is_local_base = Path(base_source).is_dir()
    is_local_proc = Path(processor_source).is_dir()

    resolved_device = device_preference.strip().lower()
    if resolved_device == "auto":
        resolved_device = "cuda" if torch.cuda.is_available() else "cpu"
    if resolved_device not in ("cpu", "cuda") or (resolved_device == "cuda" and not torch.cuda.is_available()):
        if device_preference.strip().lower() == "cuda":
            raise VLMInferenceError("Requested CUDA device for VLM, but CUDA is unavailable.")
        resolved_device = "cpu"

    if resolved_device == "cuda":
        torch.set_float32_matmul_precision("high")
        torch.backends.cuda.matmul.allow_tf32 = True
        torch.backends.cudnn.allow_tf32 = True
        if dtype_preference == "float16":
            compute_dtype = torch.float16
        elif dtype_preference == "float32":
            compute_dtype = torch.float32
        else:
            compute_dtype = torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
    else:
        compute_dtype = torch.float32

    try:
        processor = AutoProcessor.from_pretrained(
            processor_source,
            local_files_only=is_local_proc,
        )
        # If chat_template is missing on processor, check base_source
        if getattr(processor, "chat_template", None) is None and Path(base_source).is_dir():
            chat_tmpl_path = Path(processor_source) / "chat_template.jinja"
            if chat_tmpl_path.is_file():
                processor.chat_template = chat_tmpl_path.read_text(encoding="utf-8")

        img_proc = getattr(processor, "image_processor", None)
        if img_proc is not None:
            if hasattr(img_proc, "do_image_splitting"):
                img_proc.do_image_splitting = enable_image_splitting
            if (
                hasattr(img_proc, "size")
                and isinstance(img_proc.size, dict)
                and not enable_image_splitting
            ):
                img_proc.size = {"longest_edge": image_size}
    except Exception as exc:
        raise VLMInferenceError(f"Failed to load VLM processor from {processor_source}: {exc}") from exc

    load_kwargs: dict[str, Any] = {
        "dtype": compute_dtype,
        "attn_implementation": "sdpa",
        "local_files_only": is_local_base,
    }

    if resolved_device == "cuda":
        is_large = any(tag in base_source for tag in ("2B", "3B", "7B"))
        free_vram_gb = torch.cuda.mem_get_info(0)[0] / (1024**3)
        use_4bit = load_in_4bit or (is_large and free_vram_gb < 6.5)
        if use_4bit:
            load_kwargs["quantization_config"] = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_use_double_quant=True,
                bnb_4bit_quant_type="nf4",
                bnb_4bit_compute_dtype=compute_dtype,
                llm_int8_enable_fp32_cpu_offload=cpu_offload,
            )
        load_kwargs["device_map"] = "auto" if cpu_offload else {"": 0}

    try:
        base_model = AutoModelForImageTextToText.from_pretrained(base_source, **load_kwargs)
        if resolved_device == "cpu":
            base_model = base_model.to("cpu")

        if adapter_cfg_file.is_file():
            model = PeftModel.from_pretrained(
                base_model,
                str(adapter_dir),
                is_trainable=False,
                local_files_only=True,
            )
        else:
            model = base_model

        model.eval()
    except RuntimeError as exc:
        if "out of memory" in str(exc).lower():
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            raise VLMInferenceError("CUDA out of memory while loading VLM.") from exc
        raise VLMInferenceError(f"Failed to load VLM model weights: {exc}") from exc
    except Exception as exc:
        raise VLMInferenceError(f"Failed to initialize VLM model: {exc}") from exc

    return processor, model, resolved_device, compute_dtype


class MealSenseVLMService:
    """Reusable VLM service for ingredient extraction, portion estimation, and nutrition grounding."""

    def __init__(
        self,
        checkpoint: str | None = None,
        device: str | None = None,
        load_in_4bit: bool | None = None,
        nutrition_provider: NutritionValidationProvider | None = None,
    ) -> None:
        ml_cfg = load_ml_config()
        self.vlm_cfg: VLMConfig = ml_cfg.vlm
        self.checkpoint_spec: VLMCheckpointSpec = self.vlm_cfg.get_checkpoint_spec(checkpoint)
        self.device_preference = device or self.vlm_cfg.device
        self.load_in_4bit = load_in_4bit if load_in_4bit is not None else self.vlm_cfg.load_in_4bit
        self.nutrition_provider = nutrition_provider or NutritionValidationProvider(ml_cfg.nutrition)

    def inspect_checkpoint_metadata(self) -> dict[str, Any]:
        """Return inspection metadata for the configured checkpoint."""
        adapter_dir = self.checkpoint_spec.adapter_path
        adapter_cfg_path = adapter_dir / "adapter_config.json"
        adapter_cfg: dict[str, Any] = {}
        if adapter_cfg_path.is_file():
            with adapter_cfg_path.open("r", encoding="utf-8") as fh:
                adapter_cfg = json.load(fh)

        base_source = _resolve_base_model_source(self.checkpoint_spec, adapter_cfg)
        proc_source = _resolve_processor_source(self.checkpoint_spec, base_source)
        return {
            "checkpoint_name": self.checkpoint_spec.name,
            "adapter_path": str(adapter_dir),
            "exists": adapter_dir.is_dir(),
            "has_adapter_config": adapter_cfg_path.is_file(),
            "has_adapter_weights": (adapter_dir / "adapter_model.safetensors").is_file(),
            "peft_type": adapter_cfg.get("peft_type"),
            "peft_version": adapter_cfg.get("peft_version"),
            "lora_r": adapter_cfg.get("r"),
            "lora_alpha": adapter_cfg.get("lora_alpha"),
            "target_modules": adapter_cfg.get("target_modules"),
            "base_model_source": base_source,
            "processor_source": proc_source,
            "architecture": self.checkpoint_spec.architecture,
        }

    def load(self):
        adapter_dir = self.checkpoint_spec.adapter_path
        adapter_cfg_path = adapter_dir / "adapter_config.json"
        if not adapter_dir.is_dir() or not adapter_cfg_path.is_file():
            raise FileNotFoundError(
                f"VLM adapter checkpoint '{self.checkpoint_spec.name}' is missing or empty at {adapter_dir}."
            )
        with adapter_cfg_path.open("r", encoding="utf-8") as fh:
            adapter_cfg = json.load(fh)

        base_source = _resolve_base_model_source(self.checkpoint_spec, adapter_cfg)
        if not Path(base_source).is_dir() and "/" not in base_source:
            raise FileNotFoundError(f"Base VLM model not found locally at {base_source}")

        proc_source = _resolve_processor_source(self.checkpoint_spec, base_source)

        with _vlm_lock:
            return _load_cached_vlm(
                self.checkpoint_spec.name,
                str(adapter_dir.resolve()),
                proc_source,
                base_source,
                self.device_preference,
                self.vlm_cfg.dtype,
                self.load_in_4bit,
                self.vlm_cfg.cpu_offload,
                self.vlm_cfg.image_size,
                self.vlm_cfg.enable_image_splitting,
            )

    def generate_vision_analysis(
        self,
        image: str | Path | bytes | Image.Image | Any,
        predicted_label: str,
        confidence: float,
    ) -> tuple[VLMVisionOutputSchema, str]:
        """Run image-plus-text generation with the fine-tuned VLM and parse VLMVisionOutputSchema."""
        import torch

        if predicted_label not in ALLOWED_FOOD_CLASSES:
            raise ValueError(
                f"Unsupported food label '{predicted_label}'. Expected one of {ALLOWED_FOOD_CLASSES}."
            )

        rgb_image = open_and_validate_image(
            image,
            max_pixels=self.vlm_cfg.max_image_pixels,
            allowed_formats=self.vlm_cfg.allowed_formats,
        )
        target_sz = self.vlm_cfg.image_size
        if rgb_image.size != (target_sz, target_sz):
            rgb_image = rgb_image.resize((target_sz, target_sz), Image.Resampling.BICUBIC)

        processor, model, device, compute_dtype = self.load()
        kb = NINE_CLASS_KNOWLEDGE_BASE[predicted_label]
        candidates = [ing["name"] for ing in kb["ingredients"]]
        user_text = build_vlm_user_prompt(predicted_label, confidence, candidates)

        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "image"},
                    {"type": "text", "text": user_text},
                ],
            }
        ]
        prompt = processor.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
        )
        inputs = processor(
            text=[prompt],
            images=[[rgb_image]],
            padding=True,
            return_tensors="pt",
        ).to(device)

        amp_ctx = (
            torch.amp.autocast(device_type="cuda", dtype=compute_dtype)
            if device == "cuda"
            else nullcontext()
        )
        try:
            with torch.inference_mode(), amp_ctx:
                out_ids = model.generate(
                    **inputs,
                    max_new_tokens=self.vlm_cfg.max_new_tokens,
                    do_sample=self.vlm_cfg.do_sample,
                    use_cache=self.vlm_cfg.use_cache,
                )
        except RuntimeError as exc:
            if "out of memory" in str(exc).lower():
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
                raise VLMInferenceError("CUDA out of memory during VLM generation.") from exc
            raise VLMInferenceError(f"VLM generation failed: {exc}") from exc

        trimmed = [o[len(i) :] for i, o in zip(inputs["input_ids"], out_ids)]
        raw_text = processor.batch_decode(trimmed, skip_special_tokens=True)[0].strip()

        parsed_dict = extract_json_object(raw_text)
        if parsed_dict:
            try:
                validated = VLMVisionOutputSchema.model_validate(parsed_dict)
                return validated, raw_text
            except Exception as exc:
                logger.warning("VLM JSON failed strict schema validation (%s); applying safe fallback.", exc)

        # Fallback if VLM produced malformed JSON: do not fabricate visible ingredients from KB priors
        fallback = VLMVisionOutputSchema(
            dish_matches_prediction=True,
            visual_fullness_multiplier=1.0,
            portion_confidence="low",
            visible_ingredients=[],
            observed_preparation_state="",
            occluded_or_uncertain=True,
        )
        return fallback, raw_text

    def analyze(
        self,
        image: str | Path | bytes | Image.Image | Any,
        predicted_label: str,
        confidence: float,
    ) -> dict[str, Any]:
        """Perform end-to-end VLM ingredient extraction, portion estimation, and nutrition grounding."""
        vision_output, raw_text = self.generate_vision_analysis(
            image=image,
            predicted_label=predicted_label,
            confidence=confidence,
        )
        vision_dict = vision_output.model_dump()
        grounded = self.nutrition_provider.calculate_grounded_nutrition(
            dinov3_class=predicted_label,
            dinov3_confidence=confidence,
            vlm_vision_data=vision_dict,
        )
        if not extract_json_object(raw_text):
            grounded["warnings"].append(
                "VLM output required JSON recovery fallback; recipe-standard ingredient proportions were applied."
            )
            grounded["requires_user_confirmation"] = True

        # Validate complete output structure via Pydantic v2 before returning
        validated_response = StructuredNutritionResponseSchema.model_validate(grounded)
        result = validated_response.model_dump()
        result["vlm_checkpoint"] = self.checkpoint_spec.name
        result["vlm_raw_response"] = raw_text
        return result


def analyze_with_vlm(
    image: str | Path | bytes | Image.Image | Any,
    predicted_label: str,
    confidence: float,
    checkpoint: str | None = None,
    device: str | None = None,
) -> dict[str, Any]:
    """Convenience function to run VLM food-to-nutrition analysis."""
    service = MealSenseVLMService(checkpoint=checkpoint, device=device)
    return service.analyze(image=image, predicted_label=predicted_label, confidence=confidence)


def clear_vlm_cache() -> None:
    """Clear the cached VLM model and processor instances."""
    _load_cached_vlm.cache_clear()
