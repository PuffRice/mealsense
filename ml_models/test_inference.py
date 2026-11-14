#!/usr/bin/env python
"""Standalone CLI script to test DINOv3 + Fine-Tuned VLM inference without starting Django.

Usage:
    python ml_models/test_inference.py --image test_food.jpg
    python ml_models/test_inference.py --image test_food.jpg --checkpoint checkpoint-147 --device cuda
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import tempfile
import time

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PIL import Image

from ml_models.inference.classifier import classify_food_image
from ml_models.inference.pipeline import analyze_food_image


def _ensure_test_image(image_arg: str) -> tuple[Path, tempfile.TemporaryDirectory | None]:
    path = Path(image_arg)
    if path.is_file():
        return path, None

    # Check if there is a sample image in Mealsense_Models dataset
    fallback_candidates = [
        PROJECT_ROOT.parent / "Mealsense_Models" / "mealsense_local_artifacts" / "dataset" / "images" / "kacchi_biryani_01.jpg",
        PROJECT_ROOT.parent / "Mealsense_Models" / "food_dataset" / "train" / "kacchi",
    ]
    for cand in fallback_candidates:
        if cand.is_file():
            print(f"[INFO] '{image_arg}' not found; using sample food image: {cand}")
            return cand, None
        if cand.is_dir():
            imgs = sorted(cand.glob("*.jpg"))
            if imgs:
                print(f"[INFO] '{image_arg}' not found; using sample food image: {imgs[0]}")
                return imgs[0], None

    # Synthesize a temporary RGB food test image if path doesn't exist
    tmp_dir = tempfile.TemporaryDirectory()
    synth_path = Path(tmp_dir.name) / "synthetic_test_food.jpg"
    Image.new("RGB", (384, 384), color=(190, 145, 90)).save(synth_path, format="JPEG")
    print(f"[INFO] '{image_arg}' not found; generated synthetic RGB test image at {synth_path}")
    return synth_path, tmp_dir


def main() -> int:
    parser = argparse.ArgumentParser(description="Test MealSense DINOv3 + VLM Inference Pipeline")
    parser.add_argument("--image", type=str, default="test_food.jpg", help="Path to food image (JPEG/PNG/WebP)")
    parser.add_argument(
        "--checkpoint",
        type=str,
        default=None,
        help="VLM checkpoint name ('mealsense-vlm-lora' or 'checkpoint-147')",
    )
    parser.add_argument(
        "--device",
        type=str,
        default=None,
        choices=["auto", "cuda", "cpu"],
        help="Inference device ('auto', 'cuda', or 'cpu')",
    )
    parser.add_argument("--classifier-only", action="store_true", help="Run DINOv3 classifier only")
    args = parser.parse_args()

    img_path, tmp_ctx = _ensure_test_image(args.image)
    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.reset_peak_memory_stats()

        t_start = time.perf_counter()
        if args.classifier_only:
            cls_out = classify_food_image(img_path, device=args.device)
            elapsed = time.perf_counter() - t_start
            print("\n=== DINOv3 Classification Result ===")
            print(json.dumps(cls_out, indent=2))
            print(f"\nInference Time: {elapsed:.3f} s")
            return 0

        result = analyze_food_image(
            img_path,
            checkpoint=args.checkpoint,
            device=args.device,
            run_vlm=True,
        )
        total_elapsed = time.perf_counter() - t_start

        print("\n" + "=" * 64)
        print("MEALSENSE INFERENCE PIPELINE REPORT")
        print("=" * 64)
        print(f"Image Path              : {img_path}")
        print(f"VLM Checkpoint          : {result.get('vlm_checkpoint')}")
        print(f"Predicted Food Class    : {result['classification']['predicted_label']} ({result['food_name']})")
        print(f"Classification Conf.    : {result['classification']['confidence']:.4f}")
        print(f"Top Predictions         : {json.dumps(result['classification'].get('top_predictions', []))}")
        print("-" * 64)
        print("VLM Raw Response:")
        print(result.get("vlm_raw_response", ""))
        print("-" * 64)
        print(f"Estimated Portion       : {result['portion']['estimated_weight_g']} g ({result['portion']['portion_description']})")
        print("Extracted Ingredients   :")
        for ing in result["ingredients"]:
            print(
                f"  - {ing['name']:<32} : {ing['estimated_weight_g']:>6.1f} g "
                f"[{ing.get('identification', 'n/a')}] ({ing.get('nutrition_source', '')})"
            )
        print("-" * 64)
        print("Estimated Nutrition     :")
        nutr = result["nutrition"]
        print(f"  - Calories            : {nutr['calories_kcal']} kcal")
        print(f"  - Protein             : {nutr['protein_g']} g")
        print(f"  - Carbohydrates       : {nutr['carbohydrates_g']} g")
        print(f"  - Fat                 : {nutr['fat_g']} g")
        print(f"  - Fiber               : {nutr['fiber_g']} g")
        print("Micronutrients          :")
        micro = result["micronutrients"]
        print(f"  - Iron                : {micro['iron_mg']} mg")
        print(f"  - Calcium             : {micro['calcium_mg']} mg")
        print(f"  - Potassium           : {micro['potassium_mg']} mg")
        print("-" * 64)
        timing = result.get("timing", {})
        print(
            f"Inference Time          : {total_elapsed:.3f} s "
            f"(DINOv3: {timing.get('classifier_seconds', 0):.3f} s | VLM: {timing.get('vlm_seconds', 0):.3f} s)"
        )
        if torch.cuda.is_available():
            alloc_mb = torch.cuda.memory_allocated(0) / (1024**2)
            peak_mb = torch.cuda.max_memory_allocated(0) / (1024**2)
            reserved_mb = torch.cuda.memory_reserved(0) / (1024**2)
            print(
                f"GPU Memory Usage (CUDA) : Allocated={alloc_mb:.1f} MB | "
                f"Peak={peak_mb:.1f} MB | Reserved={reserved_mb:.1f} MB"
            )
        else:
            print("GPU Memory Usage        : Running on CPU")
        print("=" * 64)
        print("\nFull Structured JSON Output:")
        # Exclude raw_response from clean JSON printout or keep it concise
        clean_output = {k: v for k, v in result.items() if k not in ("vlm_raw_response",)}
        print(json.dumps(clean_output, indent=2))
        return 0
    finally:
        if tmp_ctx is not None:
            tmp_ctx.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
