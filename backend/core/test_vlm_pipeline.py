"""Automated tests for DINOv3 classifier, Fine-Tuned VLM, Nutrition Validation, Pipeline, and Django API."""
from __future__ import annotations

from decimal import Decimal
from io import BytesIO
import json
import tempfile
from unittest import skipUnless
from unittest.mock import patch

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, SimpleTestCase, TestCase, override_settings
from PIL import Image

from ml_models.inference.classifier import (
    ClassifierError,
    DINOv3FoodClassifier,
    InvalidImageError,
    classify_food_image,
    clear_classifier_cache,
)
from ml_models.inference.config import load_ml_config
from ml_models.inference.nutrition import NutritionValidationProvider, normalize_ingredient_key
from ml_models.inference.pipeline import analyze_food_image
from ml_models.inference.vlm import (
    MealSenseVLMService,
    StructuredNutritionResponseSchema,
    VLMVisionOutputSchema,
    extract_json_object,
)
from .models import FoodImage, FoodPrediction, Meal, MealItem, RecognitionResult, User


def _make_image_bytes(fmt: str = "JPEG", size: tuple[int, int] = (256, 256)) -> bytes:
    buf = BytesIO()
    Image.new("RGB", size, color=(180, 140, 90)).save(buf, format=fmt)
    return buf.getvalue()


class DINOv3ClassifierModuleTests(SimpleTestCase):
    def test_classifier_loads_and_returns_expected_schema(self):
        clear_classifier_cache()
        img_bytes = _make_image_bytes("PNG", (300, 240))
        res = classify_food_image(img_bytes, top_k=3, device="cpu")
        self.assertIn("predicted_food", res)
        self.assertIn("confidence", res)
        self.assertIn("top_predictions", res)
        self.assertEqual(len(res["top_predictions"]), 3)
        self.assertEqual(res["predicted_food"], res["top_predictions"][0]["label"])
        self.assertAlmostEqual(res["confidence"], res["top_predictions"][0]["confidence"], places=4)
        scores = [item["confidence"] for item in res["top_predictions"]]
        self.assertEqual(scores, sorted(scores, reverse=True))
        self.assertTrue(all(0.0 <= s <= 1.0 for s in scores))

    def test_classifier_rejects_invalid_images_and_bad_top_k(self):
        with self.assertRaises(InvalidImageError):
            classify_food_image(b"not-an-image", device="cpu")
        with self.assertRaises(InvalidImageError):
            buf = BytesIO()
            Image.new("RGB", (64, 64), "blue").save(buf, format="BMP")
            classify_food_image(buf.getvalue(), device="cpu")
        with self.assertRaises(ValueError):
            classify_food_image(_make_image_bytes(), top_k=0, device="cpu")

    def test_missing_checkpoint_raises_file_not_found(self):
        clf = DINOv3FoodClassifier(checkpoint_path="/nonexistent/dinov3.pth", device="cpu")
        # Override fallback path so it also fails
        object.__setattr__(clf.cfg, "fallback_checkpoint_path", clf.cfg.checkpoint_path)
        with self.assertRaises(FileNotFoundError):
            clf.classify(_make_image_bytes())


class VLMAndNutritionValidationTests(SimpleTestCase):
    def test_json_extraction_and_malformed_fallback(self):
        raw_fenced = '```json\n{"dish_matches_prediction": true, "visual_fullness_multiplier": 1.2}\n```'
        parsed = extract_json_object(raw_fenced)
        self.assertEqual(parsed.get("visual_fullness_multiplier"), 1.2)

        # Trailing comma repair
        repaired = extract_json_object('Here is output: {"dish_matches_prediction": false,}')
        self.assertEqual(repaired.get("dish_matches_prediction"), False)

        # Completely invalid text returns empty dict safely
        self.assertEqual(extract_json_object("No JSON braces here at all"), {})

    def test_checkpoint_inspection_and_switching(self):
        vlm_main = MealSenseVLMService(checkpoint="mealsense-vlm-lora")
        meta_main = vlm_main.inspect_checkpoint_metadata()
        self.assertTrue(meta_main["has_adapter_config"])
        self.assertTrue(meta_main["has_adapter_weights"])
        self.assertEqual(meta_main["peft_type"], "LORA")
        self.assertEqual(meta_main["lora_r"], 16)

        vlm_147 = MealSenseVLMService(checkpoint="checkpoint-147")
        meta_147 = vlm_147.inspect_checkpoint_metadata()
        self.assertTrue(meta_147["has_adapter_config"])
        self.assertTrue(meta_147["has_adapter_weights"])
        self.assertIn("mealsense-vlm-lora", meta_147["processor_source"])

        # Empty mealsense-qwen-vl-lora raises FileNotFoundError when attempting to load
        vlm_empty = MealSenseVLMService(checkpoint="mealsense-qwen-vl-lora")
        with self.assertRaises(FileNotFoundError):
            vlm_empty.load()

    def test_ingredient_normalization_and_fctb_grounding(self):
        self.assertEqual(normalize_ingredient_key("Cooked Rice"), "basmati_rice")
        self.assertEqual(normalize_ingredient_key("Chola"), "chickpeas_dry")
        self.assertEqual(normalize_ingredient_key("Shorshe"), "mustard_seeds")

        provider = NutritionValidationProvider()
        grounded = provider.calculate_grounded_nutrition(
            dinov3_class="kacchi",
            dinov3_confidence=0.94,
            vlm_vision_data={
                "dish_matches_prediction": True,
                "visual_fullness_multiplier": 1.0,
                "portion_confidence": "high",
                "visible_ingredients": [
                    {"name": "basmati_rice", "visual_confidence": 0.96, "estimated_volume_share": 0.48},
                    {"name": "mutton", "visual_confidence": 0.94, "estimated_volume_share": 0.30},
                    {"name": "potato", "visual_confidence": 0.91, "estimated_volume_share": 0.10},
                ],
                "observed_preparation_state": "Layered mutton kacchi biryani",
                "occluded_or_uncertain": False,
            },
        )
        # Validate against Pydantic schema
        validated = StructuredNutritionResponseSchema.model_validate(grounded)
        self.assertEqual(validated.portion.estimated_weight_g, 380.0)
        total_ing_weight = round(sum(i.estimated_weight_g for i in validated.ingredients), 1)
        self.assertAlmostEqual(total_ing_weight, 380.0, places=1)
        self.assertGreater(validated.nutrition.calories_kcal or 0, 500)
        self.assertIsNotNone(validated.micronutrients.iron_mg)

    def test_real_vlm_inference_pipeline_end_to_end(self):
        cfg = load_ml_config()
        spec = cfg.vlm.get_checkpoint_spec("mealsense-vlm-lora")
        if not (spec.adapter_path / "adapter_model.safetensors").is_file():
            self.skipTest("VLM LoRA adapter weights not present")

        img_bytes = _make_image_bytes("JPEG", (384, 384))
        result = analyze_food_image(img_bytes, checkpoint="mealsense-vlm-lora")
        self.assertIn("food_name", result)
        self.assertIn("classification", result)
        self.assertIn("portion", result)
        self.assertIn("ingredients", result)
        self.assertIn("nutrition", result)
        self.assertIn("micronutrients", result)
        self.assertIn("confidence", result)
        self.assertIn("timing", result)


@override_settings(AI_PROVIDER="dinov3_vlm", AI_DINOV3_DEVICE="cpu")
class PipelineDjangoApiIntegrationTests(TestCase):
    def setUp(self):
        self.client = Client(enforce_csrf_checks=True)
        self.user = User.objects.create_user(email="vlm_tester@example.com", password="secure-password-123")
        self.client.get("/api/v1/auth/csrf/")
        self.csrf = self.client.cookies["csrftoken"].value
        login_res = self.client.post(
            "/api/v1/auth/login/",
            data=json.dumps({"identifier": self.user.email, "password": "secure-password-123"}),
            content_type="application/json",
            HTTP_X_CSRFTOKEN=self.csrf,
        )
        self.assertEqual(login_res.status_code, 200)
        self.client.get("/api/v1/auth/csrf/")
        self.csrf = self.client.cookies["csrftoken"].value

    def _mock_pipeline_output(self):
        provider = NutritionValidationProvider()
        grounded = provider.calculate_grounded_nutrition(
            dinov3_class="biriyani",
            dinov3_confidence=0.93,
            vlm_vision_data={
                "dish_matches_prediction": True,
                "visual_fullness_multiplier": 1.0,
                "portion_confidence": "high",
                "visible_ingredients": [
                    {"name": "basmati_rice", "visual_confidence": 0.96, "estimated_volume_share": 0.52},
                    {"name": "chicken_meat", "visual_confidence": 0.92, "estimated_volume_share": 0.28},
                    {"name": "potato", "visual_confidence": 0.88, "estimated_volume_share": 0.09},
                ],
                "observed_preparation_state": "Spiced chicken biryani",
                "occluded_or_uncertain": False,
            },
        )
        grounded["classification"]["top_predictions"] = [
            {"label": "biriyani", "confidence": 0.93},
            {"label": "kacchi", "confidence": 0.05},
        ]
        grounded["vlm_checkpoint"] = "mealsense-vlm-lora"
        return grounded

    def test_recognitions_upload_with_vlm_and_save_analyzed_meal(self):
        mock_out = self._mock_pipeline_output()
        with tempfile.TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=media_root):
            with patch("ml_models.inference.pipeline.analyze_food_image", return_value=mock_out):
                upload = SimpleUploadedFile("biriyani.jpg", _make_image_bytes("JPEG"), content_type="image/jpeg")
                response = self.client.post(
                    "/api/v1/recognitions/",
                    data={"image": upload},
                    HTTP_X_CSRFTOKEN=self.csrf,
                )
                self.assertEqual(response.status_code, 201, response.content)
                body = response.json()
                self.assertEqual(body["status"], "completed")
                self.assertIn("analysis", body)
                self.assertEqual(body["analysis"]["classification"]["predicted_label"], "biriyani")
                self.assertEqual(body["analysis"]["portion"]["estimated_weight_g"], 350.0)
                rec_id = body["id"]

                # Save analyzed meal via POST /api/v1/recognitions/<id>/ with action='save_meal'
                save_res = self.client.post(
                    f"/api/v1/recognitions/{rec_id}/",
                    data=json.dumps({
                        "action": "save_meal",
                        "meal_type": "lunch",
                        "notes": "AI VLM analyzed biryani",
                        "portion_weight_g": "350.00",
                    }),
                    content_type="application/json",
                    HTTP_X_CSRFTOKEN=self.csrf,
                )
                self.assertEqual(save_res.status_code, 201, save_res.content)
                saved_payload = save_res.json()
                self.assertIn("meal", saved_payload)
                meal_id = saved_payload["meal"]["id"]
                meal = Meal.objects.get(pk=meal_id, user=self.user)
                items = list( MealItem.objects.filter(meal=meal) )
                self.assertEqual(len(items), 7)  # 7 grounded ingredients for biriyani
                total_grams = sum((item.grams for item in items), Decimal("0"))
                self.assertEqual(total_grams, Decimal("350.00"))
                total_kcal = sum((item.kcal for item in items), Decimal("0"))
                self.assertGreater(total_kcal, Decimal("400.00"))
