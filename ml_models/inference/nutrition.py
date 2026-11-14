"""Modular Nutrition Validation & Food Composition Grounding Service.

Grounds VLM-extracted and recipe-inferred ingredients against verified food
composition data (FCTB 2013 - Institute of Nutrition and Food Science, University
of Dhaka) and/or the Django catalog, preserving provenance and distinguishing
model estimates from source-backed composition values.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import sqlite3
from typing import Any

from .config import NutritionProviderConfig, load_ml_config

FAO_RECIPE_SOURCE = (
    "https://www.fao.org/fileadmin/templates/food_composition/documents/FCT_10_2_14_final_version.pdf"
)

ALLOWED_FOOD_CLASSES: tuple[str, ...] = (
    "bakorkhani",
    "beguni",
    "biriyani",
    "chickpeas",
    "egg_omlete",
    "fuchka",
    "haleem",
    "hilsha_fish",
    "kacchi",
)

# Verified FCTB 2013 (INFS, University of Dhaka) per-100g raw edible portion records
# Columns: (key, display_name, fctb_code, cooking_yield_factor, kcal_100g, protein_g, carbs_g, fat_g, fiber_g, iron_mg, calcium_mg, potassium_mg, citation)
FCTB_2013_EXTENDED: tuple[
    tuple[str, str, str, float, float, float, float, float, float | None, float | None, float | None, float | None, str],
    ...,
] = (
    ("wheat_flour_maida", "Refined Wheat Flour (Maida), raw", "01_0023", 0.90, 348.0, 11.0, 74.1, 0.9, 2.7, 2.7, 23.0, 130.0, "FCTB 2013 (Code 01_0023) - INFS, DU"),
    ("basmati_rice", "Rice, aromatic/parboiled (Chinigura/Basmati), raw", "01_0012", 2.75, 349.0, 7.5, 77.4, 0.8, 1.4, 1.0, 10.0, 115.0, "FCTB 2013 (Code 01_0012) - INFS, DU"),
    ("chickpeas_dry", "Chickpea (Chola/Boot), whole dried, raw", "02_0003", 2.40, 347.0, 20.8, 55.0, 5.1, 12.2, 4.6, 150.0, 718.0, "FCTB 2013 (Code 02_0003) - INFS, DU"),
    ("besan_gram_flour", "Bengal Gram Flour (Besan), raw", "02_0004", 1.00, 372.0, 22.0, 58.2, 5.6, 10.8, 5.3, 56.0, 846.0, "FCTB 2013 (Code 02_0004) - INFS, DU"),
    ("mixed_lentils", "Mixed Lentils (Masoor, Moong, Mashkalai), raw", "02_0008", 2.50, 336.0, 24.3, 55.8, 1.1, 10.5, 6.5, 68.0, 670.0, "FCTB 2013 (Group 02 Pulses) - INFS, DU"),
    ("broken_wheat", "Broken Wheat (Gom/Dalia), raw", "01_0021", 2.60, 341.0, 11.8, 71.2, 1.5, 11.2, 4.9, 41.0, 360.0, "FCTB 2013 (Code 01_0021) - INFS, DU"),
    ("eggplant", "Brinjal / Eggplant (Begun), purple, raw", "03_0007", 0.85, 25.0, 1.4, 4.2, 0.3, 3.0, 0.4, 18.0, 200.0, "FCTB 2013 (Code 03_0007) - INFS, DU"),
    ("potato", "Potato, local (Gol Alu), raw", "05_0001", 0.92, 66.0, 1.3, 14.8, 0.1, 1.7, 0.5, 11.0, 380.0, "FCTB 2013 (Code 05_0001) - INFS, DU"),
    ("onion", "Onion (Peyaj), raw", "07_0012", 0.65, 50.0, 1.4, 10.6, 0.1, 1.9, 0.6, 47.0, 157.0, "FCTB 2013 (Code 07_0012) - INFS, DU"),
    ("green_chili", "Chili, green, raw", "07_0003", 0.95, 41.0, 2.6, 6.1, 0.6, 4.8, 1.4, 30.0, 340.0, "FCTB 2013 (Code 07_0003) - INFS, DU"),
    ("tamarind_pulp", "Tamarind pulp (Tetul), ripe", "04_0042", 1.00, 283.0, 3.1, 67.4, 0.1, 5.1, 2.8, 74.0, 628.0, "FCTB 2013 (Code 04_0042) - INFS, DU"),
    ("mustard_seeds", "Mustard seeds (Shorshe), dried", "06_0007", 1.80, 508.0, 20.2, 21.6, 39.7, 12.2, 9.2, 266.0, 738.0, "FCTB 2013 (Code 06_0007) - INFS, DU"),
    ("mixed_spices", "Bangladeshi Garam Masala & Spices", "07_0005", 1.00, 354.0, 13.5, 44.2, 14.0, 25.0, 16.0, 450.0, 1100.0, "FCTB 2013 (Group 07 Spices) - INFS, DU"),
    ("hilsa_fish", "Hilsa Fish (Ilish), raw edible portion", "09_0028", 0.82, 273.0, 21.8, 0.0, 19.4, 0.0, 1.9, 180.0, 280.0, "FCTB 2013 (Code 09_0028) - INFS, DU"),
    ("chicken_meat", "Chicken meat, broiler, raw", "10_0008", 0.74, 145.0, 21.8, 0.0, 6.4, 0.0, 1.1, 12.0, 240.0, "FCTB 2013 (Code 10_0008) - INFS, DU"),
    ("mutton", "Goat meat (Mutton/Khashi), moderate fat, raw", "10_0006", 0.72, 194.0, 21.4, 0.0, 12.1, 0.0, 2.8, 12.0, 310.0, "FCTB 2013 (Code 10_0006) - INFS, DU"),
    ("beef", "Beef, moderate fat, raw", "10_0002", 0.70, 226.0, 20.6, 0.0, 15.9, 0.0, 2.6, 11.0, 318.0, "FCTB 2013 (Code 10_0002) - INFS, DU"),
    ("chicken_egg", "Hen Egg (Murgi Dim), whole, raw", "11_0002", 0.92, 158.0, 13.3, 0.6, 11.5, 0.0, 1.8, 50.0, 132.0, "FCTB 2013 (Code 11_0002) - INFS, DU"),
    ("yogurt", "Curd / Yogurt (Doi), whole milk", "12_0005", 1.00, 97.0, 3.5, 11.4, 4.1, 0.0, 0.2, 149.0, 180.0, "FCTB 2013 (Code 12_0005) - INFS, DU"),
    ("ghee", "Ghee / Clarified Butter", "13_0002", 1.00, 898.0, 0.0, 0.0, 99.8, 0.0, 0.0, 0.0, 0.0, "FCTB 2013 (Code 13_0002) - INFS, DU"),
    ("soybean_oil", "Soybean cooking oil", "13_0008", 1.00, 900.0, 0.0, 0.0, 100.0, 0.0, 0.0, 0.0, 0.0, "FCTB 2013 (Code 13_0008) - INFS, DU"),
    ("mustard_oil", "Mustard oil (Khati Shorsher Tel)", "13_0005", 1.00, 900.0, 0.0, 0.0, 100.0, 0.0, 0.0, 0.0, 0.0, "FCTB 2013 (Code 13_0005) - INFS, DU"),
    ("sugar", "Sugar, white refined", "14_0003", 1.00, 398.0, 0.0, 99.4, 0.0, 0.0, 0.1, 1.0, 2.0, "FCTB 2013 (Code 14_0003) - INFS, DU"),
)

# Synonym mapping for ingredient normalization
INGREDIENT_SYNONYMS: dict[str, str] = {
    "cooked_rice": "basmati_rice",
    "rice": "basmati_rice",
    "chinigura_rice": "basmati_rice",
    "polao_rice": "basmati_rice",
    "chicken": "chicken_meat",
    "broiler_chicken": "chicken_meat",
    "goat_meat": "mutton",
    "khashi": "mutton",
    "lamb": "mutton",
    "egg": "chicken_egg",
    "hen_egg": "chicken_egg",
    "dim": "chicken_egg",
    "brinjal": "eggplant",
    "begun": "eggplant",
    "chola": "chickpeas_dry",
    "chickpeas": "chickpeas_dry",
    "chickpea": "chickpeas_dry",
    "besan": "besan_gram_flour",
    "gram_flour": "besan_gram_flour",
    "maida": "wheat_flour_maida",
    "wheat_flour": "wheat_flour_maida",
    "flour": "wheat_flour_maida",
    "lentils": "mixed_lentils",
    "dal": "mixed_lentils",
    "wheat": "broken_wheat",
    "dalia": "broken_wheat",
    "alu": "potato",
    "potatoes": "potato",
    "peyaj": "onion",
    "chili": "green_chili",
    "green_chillies": "green_chili",
    "tetul": "tamarind_pulp",
    "tamarind": "tamarind_pulp",
    "shorshe": "mustard_seeds",
    "mustard": "mustard_seeds",
    "mustard_paste": "mustard_seeds",
    "spices": "mixed_spices",
    "garam_masala": "mixed_spices",
    "ilish": "hilsa_fish",
    "hilsha": "hilsa_fish",
    "hilsa": "hilsa_fish",
    "doi": "yogurt",
    "curd": "yogurt",
    "saffron_milk": "yogurt",
    "milk": "yogurt",
    "lamb_curry": "mutton",
    "mutton_curry": "mutton",
    "beef_curry": "beef",
    "chicken_curry": "chicken_meat",
    "cooking_oil": "soybean_oil",
    "oil": "soybean_oil",
    "vegetable_oil": "soybean_oil",
    "clarified_butter": "ghee",
}

DISH_CLASS_ALIASES: dict[str, str] = {
    "bakarkhani": "bakorkhani",
    "bakorkhani": "bakorkhani",
    "beguni": "beguni",
    "eggplant_fritter": "beguni",
    "biryani": "biriyani",
    "biriyani": "biriyani",
    "chicken_biryani": "biriyani",
    "chicken_biriyani": "biriyani",
    "beef_biryani": "biriyani",
    "beef_biriyani": "biriyani",
    "tehari": "biriyani",
    "polao": "biriyani",
    "pulao": "biriyani",
    "kacchi": "kacchi",
    "kacchi_biryani": "kacchi",
    "kacchi_biriyani": "kacchi",
    "mutton_biryani": "kacchi",
    "mutton_biriyani": "kacchi",
    "lamb_biryani": "kacchi",
    "chickpeas": "chickpeas",
    "chola": "chickpeas",
    "chola_bhuna": "chickpeas",
    "egg_omelette": "egg_omlete",
    "egg_omlete": "egg_omlete",
    "omelette": "egg_omlete",
    "dim_bhaji": "egg_omlete",
    "fuchka": "fuchka",
    "phuchka": "fuchka",
    "chotpoti": "fuchka",
    "haleem": "haleem",
    "halim": "haleem",
    "mutton_haleem": "haleem",
    "beef_haleem": "haleem",
    "hilsha_fish": "hilsha_fish",
    "hilsa_fish": "hilsha_fish",
    "shorshe_ilish": "hilsha_fish",
    "ilish": "hilsha_fish",
}

NINE_CLASS_KNOWLEDGE_BASE: dict[str, dict[str, Any]] = {
    "bakorkhani": {
        "food_name": "Old Dhaka Bakorkhani",
        "canonical_catalog_name": "Bakarkhani",
        "standard_serving_g": 80.0,
        "portion_description": "Two medium pieces (standard serving)",
        "recipe_source": FAO_RECIPE_SOURCE,
        "preparation": "Layered unleavened flatbread baked in a clay tandoor with maida, ghee/oil, and sugar.",
        "ingredients": [
            {"name": "wheat_flour_maida", "display_name": "Refined wheat flour (Maida)", "ratio": 0.72, "identification": "visible", "conf": 0.96},
            {"name": "ghee", "display_name": "Ghee", "ratio": 0.18, "identification": "recipe_inferred", "conf": 0.88},
            {"name": "soybean_oil", "display_name": "Soybean oil", "ratio": 0.06, "identification": "recipe_inferred", "conf": 0.85},
            {"name": "sugar", "display_name": "Sugar", "ratio": 0.04, "identification": "recipe_inferred", "conf": 0.85},
        ],
    },
    "beguni": {
        "food_name": "Beguni (Battered Fried Eggplant)",
        "canonical_catalog_name": "Beguni",
        "standard_serving_g": 100.0,
        "portion_description": "Two to three fried pieces (one medium serving)",
        "recipe_source": FAO_RECIPE_SOURCE,
        "preparation": "Thinly sliced purple eggplant dipped in spiced Bengal gram flour (besan) batter and deep-fried.",
        "ingredients": [
            {"name": "eggplant", "display_name": "Eggplant (Begun)", "ratio": 0.52, "identification": "visible", "conf": 0.94},
            {"name": "besan_gram_flour", "display_name": "Bengal gram flour (Besan)", "ratio": 0.30, "identification": "visible", "conf": 0.95},
            {"name": "soybean_oil", "display_name": "Cooking oil", "ratio": 0.15, "identification": "recipe_inferred", "conf": 0.88},
            {"name": "mixed_spices", "display_name": "Mixed spices", "ratio": 0.03, "identification": "recipe_inferred", "conf": 0.82},
        ],
    },
    "biriyani": {
        "food_name": "Bangladeshi Chicken/Beef Biriyani",
        "canonical_catalog_name": "Biryani",
        "standard_serving_g": 350.0,
        "portion_description": "One medium plate",
        "recipe_source": FAO_RECIPE_SOURCE,
        "preparation": "Aromatic Chinigura/Basmati rice cooked with spiced chicken or beef, potatoes, onion beresta, and ghee.",
        "ingredients": [
            {"name": "basmati_rice", "display_name": "Cooked aromatic rice", "ratio": 0.52, "identification": "visible", "conf": 0.96},
            {"name": "chicken_meat", "display_name": "Chicken meat", "ratio": 0.28, "identification": "visible", "conf": 0.92},
            {"name": "potato", "display_name": "Potato", "ratio": 0.09, "identification": "visible", "conf": 0.88},
            {"name": "onion", "display_name": "Fried onion (Beresta)", "ratio": 0.04, "identification": "recipe_inferred", "conf": 0.84},
            {"name": "ghee", "display_name": "Ghee", "ratio": 0.04, "identification": "recipe_inferred", "conf": 0.84},
            {"name": "yogurt", "display_name": "Yogurt (Doi)", "ratio": 0.02, "identification": "recipe_inferred", "conf": 0.80},
            {"name": "mixed_spices", "display_name": "Biryani spices", "ratio": 0.01, "identification": "recipe_inferred", "conf": 0.80},
        ],
    },
    "chickpeas": {
        "food_name": "Chola Bhuna (Spiced Chickpeas)",
        "canonical_catalog_name": "Chickpeas",
        "standard_serving_g": 160.0,
        "portion_description": "One medium bowl",
        "recipe_source": FAO_RECIPE_SOURCE,
        "preparation": "Boiled brown chickpeas sauteed with diced potatoes, chopped onions, green chilies, and roasted spices.",
        "ingredients": [
            {"name": "chickpeas_dry", "display_name": "Boiled chickpeas (Chola)", "ratio": 0.68, "identification": "visible", "conf": 0.96},
            {"name": "potato", "display_name": "Diced potato", "ratio": 0.14, "identification": "visible", "conf": 0.89},
            {"name": "onion", "display_name": "Chopped onion", "ratio": 0.08, "identification": "visible", "conf": 0.90},
            {"name": "green_chili", "display_name": "Green chili", "ratio": 0.02, "identification": "visible", "conf": 0.88},
            {"name": "soybean_oil", "display_name": "Cooking oil", "ratio": 0.06, "identification": "recipe_inferred", "conf": 0.85},
            {"name": "mixed_spices", "display_name": "Mixed spices", "ratio": 0.02, "identification": "recipe_inferred", "conf": 0.82},
        ],
    },
    "egg_omlete": {
        "food_name": "Bangladeshi Dim Bhaji (Spiced Egg Omelette)",
        "canonical_catalog_name": "Egg omelette",
        "standard_serving_g": 75.0,
        "portion_description": "One single-egg omelette",
        "recipe_source": FAO_RECIPE_SOURCE,
        "preparation": "Beaten hen eggs pan-fried in oil with finely sliced onions and green chilies.",
        "ingredients": [
            {"name": "chicken_egg", "display_name": "Hen egg", "ratio": 0.76, "identification": "visible", "conf": 0.97},
            {"name": "onion", "display_name": "Sliced onion", "ratio": 0.12, "identification": "visible", "conf": 0.91},
            {"name": "green_chili", "display_name": "Green chili", "ratio": 0.03, "identification": "visible", "conf": 0.89},
            {"name": "soybean_oil", "display_name": "Cooking oil", "ratio": 0.09, "identification": "recipe_inferred", "conf": 0.86},
        ],
    },
    "fuchka": {
        "food_name": "Bangladeshi Fuchka with Tetul Tok",
        "canonical_catalog_name": "Fuchka",
        "standard_serving_g": 180.0,
        "portion_description": "One standard plate (6-8 shells with filling)",
        "recipe_source": FAO_RECIPE_SOURCE,
        "preparation": "Crisp fried wheat shells stuffed with mashed spiced potatoes, chickpeas, grated egg, onion, and sour tamarind water.",
        "ingredients": [
            {"name": "potato", "display_name": "Spiced mashed potato", "ratio": 0.36, "identification": "visible", "conf": 0.92},
            {"name": "chickpeas_dry", "display_name": "Boiled chickpeas", "ratio": 0.20, "identification": "visible", "conf": 0.90},
            {"name": "wheat_flour_maida", "display_name": "Fried crisp wheat shells", "ratio": 0.18, "identification": "visible", "conf": 0.95},
            {"name": "tamarind_pulp", "display_name": "Tamarind water (Tetul tok)", "ratio": 0.10, "identification": "visible", "conf": 0.88},
            {"name": "chicken_egg", "display_name": "Grated boiled egg", "ratio": 0.06, "identification": "visible", "conf": 0.87},
            {"name": "onion", "display_name": "Chopped onion", "ratio": 0.04, "identification": "visible", "conf": 0.88},
            {"name": "soybean_oil", "display_name": "Frying oil", "ratio": 0.06, "identification": "recipe_inferred", "conf": 0.84},
        ],
    },
    "haleem": {
        "food_name": "Bangladeshi Shahi Mutton/Beef Haleem",
        "canonical_catalog_name": "Haleem",
        "standard_serving_g": 280.0,
        "portion_description": "One medium bowl",
        "recipe_source": FAO_RECIPE_SOURCE,
        "preparation": "Slow-cooked savory porridge of mixed lentils, broken wheat, and tender beef/mutton garnished with fried onions and green chilies.",
        "ingredients": [
            {"name": "beef", "display_name": "Beef / Mutton chunks", "ratio": 0.34, "identification": "visible", "conf": 0.91},
            {"name": "mixed_lentils", "display_name": "Mixed lentils (Dal)", "ratio": 0.32, "identification": "visible", "conf": 0.93},
            {"name": "broken_wheat", "display_name": "Broken wheat (Dalia)", "ratio": 0.18, "identification": "recipe_inferred", "conf": 0.86},
            {"name": "onion", "display_name": "Fried onion garnish", "ratio": 0.06, "identification": "visible", "conf": 0.90},
            {"name": "green_chili", "display_name": "Sliced green chili", "ratio": 0.02, "identification": "visible", "conf": 0.88},
            {"name": "soybean_oil", "display_name": "Cooking oil", "ratio": 0.06, "identification": "recipe_inferred", "conf": 0.84},
            {"name": "mixed_spices", "display_name": "Haleem masala spices", "ratio": 0.02, "identification": "recipe_inferred", "conf": 0.84},
        ],
    },
    "hilsha_fish": {
        "food_name": "Shorshe Ilish / Fried Hilsha Fish",
        "canonical_catalog_name": "Hilsa fish",
        "standard_serving_g": 180.0,
        "portion_description": "One medium fish steak with mustard gravy",
        "recipe_source": FAO_RECIPE_SOURCE,
        "preparation": "Hilsa fish steak cooked in pungent mustard seed paste, mustard oil, and whole green chilies.",
        "ingredients": [
            {"name": "hilsa_fish", "display_name": "Hilsa fish (Ilish)", "ratio": 0.68, "identification": "visible", "conf": 0.97},
            {"name": "mustard_seeds", "display_name": "Mustard paste (Shorshe)", "ratio": 0.12, "identification": "visible", "conf": 0.89},
            {"name": "green_chili", "display_name": "Whole green chili", "ratio": 0.04, "identification": "visible", "conf": 0.91},
            {"name": "mustard_oil", "display_name": "Mustard oil", "ratio": 0.10, "identification": "recipe_inferred", "conf": 0.88},
            {"name": "onion", "display_name": "Onion paste", "ratio": 0.06, "identification": "recipe_inferred", "conf": 0.82},
        ],
    },
    "kacchi": {
        "food_name": "Old Dhaka Mutton Kacchi Biryani",
        "canonical_catalog_name": "Kacchi Biryani",
        "standard_serving_g": 380.0,
        "portion_description": "One standard serving plate",
        "recipe_source": FAO_RECIPE_SOURCE,
        "preparation": "Raw marinated mutton layered with Chinigura/Basmati rice and fried potatoes slow-cooked in a sealed pot with ghee and yogurt.",
        "ingredients": [
            {"name": "basmati_rice", "display_name": "Cooked Chinigura/Basmati rice", "ratio": 0.48, "identification": "visible", "conf": 0.96},
            {"name": "mutton", "display_name": "Mutton (Khashi)", "ratio": 0.30, "identification": "visible", "conf": 0.94},
            {"name": "potato", "display_name": "Spiced potato", "ratio": 0.10, "identification": "visible", "conf": 0.91},
            {"name": "yogurt", "display_name": "Yogurt marinade", "ratio": 0.04, "identification": "recipe_inferred", "conf": 0.86},
            {"name": "ghee", "display_name": "Ghee", "ratio": 0.04, "identification": "recipe_inferred", "conf": 0.86},
            {"name": "onion", "display_name": "Fried onion (Beresta)", "ratio": 0.03, "identification": "recipe_inferred", "conf": 0.84},
            {"name": "mixed_spices", "display_name": "Kacchi masala spices", "ratio": 0.01, "identification": "recipe_inferred", "conf": 0.82},
        ],
    },
}


@dataclass(frozen=True, slots=True)
class VerifiedIngredientRecord:
    ingredient_key: str
    display_name: str
    fctb_code: str
    cooking_yield_factor: float
    calories_kcal_100g: float
    protein_g_100g: float
    carbohydrates_g_100g: float
    fat_g_100g: float
    fiber_g_100g: float | None
    iron_mg_100g: float | None
    calcium_mg_100g: float | None
    potassium_mg_100g: float | None
    source_citation: str


def normalize_ingredient_key(raw_name: str) -> str:
    """Normalize an arbitrary ingredient label to a canonical FCTB key."""
    cleaned = re.sub(r"[^a-z0-9]+", "_", str(raw_name).strip().lower()).strip("_")
    if cleaned in INGREDIENT_SYNONYMS:
        return INGREDIENT_SYNONYMS[cleaned]
    return cleaned


class NutritionValidationProvider:
    """Queries verified FCTB 2013 composition records (with SQLite & in-memory cache)."""

    def __init__(self, cfg: NutritionProviderConfig | None = None) -> None:
        self.cfg = cfg or load_ml_config().nutrition
        self._memory_cache: dict[str, VerifiedIngredientRecord] = {
            row[0]: VerifiedIngredientRecord(*row) for row in FCTB_2013_EXTENDED
        }

    def is_enabled(self) -> bool:
        return self.cfg.provider not in ("none", "off", "disabled", "")

    def lookup(self, ingredient_name: str) -> VerifiedIngredientRecord | None:
        if not self.is_enabled():
            return None

        key = normalize_ingredient_key(ingredient_name)
        if key in self._memory_cache:
            return self._memory_cache[key]

        # Check SQLite DB if configured and present
        db_path: Path = self.cfg.sqlite_db_path
        if db_path and db_path.is_file():
            try:
                with sqlite3.connect(db_path) as conn:
                    conn.row_factory = sqlite3.Row
                    row = conn.execute(
                        "SELECT * FROM nutrition_fctb WHERE ingredient_key = ?",
                        (key,),
                    ).fetchone()
                    if row is not None:
                        rec = VerifiedIngredientRecord(
                            ingredient_key=row["ingredient_key"],
                            display_name=row["display_name"],
                            fctb_code=row["fctb_code"],
                            cooking_yield_factor=float(row["cooking_yield_factor"]),
                            calories_kcal_100g=float(row["calories_kcal_100g"]),
                            protein_g_100g=float(row["protein_g_100g"]),
                            carbohydrates_g_100g=float(row["carbohydrates_g_100g"]),
                            fat_g_100g=float(row["fat_g_100g"]),
                            fiber_g_100g=None,
                            iron_mg_100g=None,
                            calcium_mg_100g=None,
                            potassium_mg_100g=None,
                            source_citation=row["source_citation"],
                        )
                        self._memory_cache[key] = rec
                        return rec
            except Exception:
                pass

        return None

    def resolve_dish_class(self, raw_label: str) -> str | None:
        cleaned = re.sub(r"[^a-z0-9]+", "_", str(raw_label).strip().lower()).strip("_")
        if cleaned in NINE_CLASS_KNOWLEDGE_BASE:
            return cleaned
        if cleaned in DISH_CLASS_ALIASES:
            return DISH_CLASS_ALIASES[cleaned]
        for alias_key, target_cls in DISH_CLASS_ALIASES.items():
            if alias_key in cleaned:
                return target_cls
        return None

    def estimate_for_any_label(
        self,
        raw_label: str,
        display_name: str,
        confidence: float,
    ) -> dict[str, Any] | None:
        """Return grounded FCTB nutrition analysis for any dish class, dish alias, or single ingredient."""
        dish_cls = self.resolve_dish_class(raw_label) or self.resolve_dish_class(display_name)
        if dish_cls is not None:
            return self.calculate_grounded_nutrition(
                dinov3_class=dish_cls,
                dinov3_confidence=confidence,
                vlm_vision_data={},
            )

        rec = self.lookup(raw_label) or self.lookup(display_name)
        if rec is None:
            return None

        serving_g = 150.0
        yield_factor = max(0.1, rec.cooking_yield_factor)
        raw_equiv_g = serving_g / yield_factor
        factor = raw_equiv_g / 100.0
        kcal = round(factor * rec.calories_kcal_100g, 1)
        prot = round(factor * rec.protein_g_100g, 1)
        carb = round(factor * rec.carbohydrates_g_100g, 1)
        fat = round(factor * rec.fat_g_100g, 1)
        fiber = round(factor * rec.fiber_g_100g, 1) if rec.fiber_g_100g is not None else None

        return {
            "food_name": display_name or rec.display_name,
            "canonical_catalog_name": display_name or rec.display_name,
            "food_class": rec.ingredient_key,
            "classification": {
                "predicted_label": rec.ingredient_key,
                "confidence": round(float(confidence), 4),
            },
            "portion": {
                "estimated_weight_g": serving_g,
                "portion_description": "One standard serving (150 g)",
                "weight_range_g": [120.0, 180.0],
                "fullness_multiplier": 1.0,
                "is_approximate": True,
            },
            "ingredients": [
                {
                    "name": rec.display_name,
                    "ingredient_key": rec.ingredient_key,
                    "estimated_weight_g": serving_g,
                    "identification": "visible",
                    "confidence": round(float(confidence), 2),
                    "nutrition_source": rec.source_citation,
                    "recipe_source": FAO_RECIPE_SOURCE,
                    "calories_kcal": kcal,
                    "protein_g": prot,
                    "carbohydrates_g": carb,
                    "fat_g": fat,
                }
            ],
            "ingredient_breakdown": [
                {
                    "name": rec.ingredient_key,
                    "weight_g": serving_g,
                    "identification": "visible",
                    "confidence": round(float(confidence), 2),
                    "nutrition_source": rec.source_citation,
                    "recipe_source": FAO_RECIPE_SOURCE,
                }
            ],
            "nutrition": {
                "calories_kcal": kcal,
                "protein_g": prot,
                "carbohydrates_g": carb,
                "fat_g": fat,
                "fiber_g": fiber,
            },
            "micronutrients": {
                "iron_mg": round(factor * rec.iron_mg_100g, 2) if rec.iron_mg_100g is not None else None,
                "calcium_mg": round(factor * rec.calcium_mg_100g, 1) if rec.calcium_mg_100g is not None else None,
                "potassium_mg": round(factor * rec.potassium_mg_100g, 1) if rec.potassium_mg_100g is not None else None,
            },
            "confidence": {
                "food_identification": round(float(confidence), 4),
                "portion_estimation": 0.72,
                "nutrition_estimation": round(float(confidence) * 0.85, 2),
            },
            "provenance": {
                "status": "grounded_fctb_2013",
                "is_verified_database": True,
                "is_approximate": True,
                "sources": [rec.source_citation],
                "vlm_raw_estimates": {},
            },
            "observed_preparation_state": "Standard cooked serving",
            "occluded_or_uncertain": False,
            "requires_user_confirmation": True,
            "warnings": [],
            "explanation": f"Approximate nutritional composition for {display_name} ({serving_g} g) grounded in {rec.source_citation}.",
        }

    def calculate_grounded_nutrition(
        self,
        dinov3_class: str,
        dinov3_confidence: float,
        vlm_vision_data: dict[str, Any],
    ) -> dict[str, Any]:
        """Combine VLM visual extraction with verified food composition data."""
        kb = NINE_CLASS_KNOWLEDGE_BASE.get(dinov3_class)
        if kb is None:
            raise ValueError(f"Unsupported food class '{dinov3_class}'.")

        fullness = float(vlm_vision_data.get("visual_fullness_multiplier", 1.0) or 1.0)
        fullness = max(0.25, min(3.0, fullness))
        portion_conf_label = str(vlm_vision_data.get("portion_confidence", "medium")).lower()
        portion_conf_score = {"high": 0.85, "medium": 0.72, "low": 0.50}.get(portion_conf_label, 0.72)

        est_serving_g = round(kb["standard_serving_g"] * fullness, 1)
        weight_range_g = [round(est_serving_g * 0.85, 1), round(est_serving_g * 1.15, 1)]

        visible_items = vlm_vision_data.get("visible_ingredients") or []
        visible_map: dict[str, dict[str, Any]] = {}
        for item in visible_items:
            if isinstance(item, dict) and item.get("name"):
                norm_k = normalize_ingredient_key(item["name"])
                visible_map[norm_k] = item

        # Compute normalized shares so ingredient weights sum consistently to est_serving_g
        raw_shares: list[tuple[dict[str, Any], float, float]] = []
        for ing in kb["ingredients"]:
            key = ing["name"]
            v_obs = visible_map.get(key)
            vol_share = (
                float(v_obs.get("estimated_volume_share", 0.0))
                if v_obs and float(v_obs.get("estimated_volume_share", 0.0)) > 0
                else float(ing["ratio"])
            )
            vis_conf = (
                float(v_obs.get("visual_confidence", ing["conf"]))
                if v_obs
                else float(ing["conf"])
            )
            raw_shares.append((ing, vol_share, vis_conf))

        total_share = sum(s for _, s, _ in raw_shares) or 1.0

        total_kcal = 0.0
        total_prot = 0.0
        total_carb = 0.0
        total_fat = 0.0
        total_fiber = 0.0
        has_fiber = False
        total_iron = 0.0
        has_iron = False
        total_calcium = 0.0
        has_calcium = False
        total_potassium = 0.0
        has_potassium = False

        ingredients_list: list[dict[str, Any]] = []
        detailed_breakdown: list[dict[str, Any]] = []
        sources_set: set[str] = {kb["recipe_source"]}
        warnings: list[str] = []
        all_grounded = True

        allocated_g = 0.0
        for idx, (ing, share, vis_conf) in enumerate(raw_shares):
            norm_share = share / total_share
            if idx == len(raw_shares) - 1:
                w_cooked = round(max(0.5, est_serving_g - allocated_g), 1)
            else:
                w_cooked = round(est_serving_g * norm_share, 1)
                allocated_g += w_cooked

            rec = self.lookup(ing["name"])
            ing_kcal = ing_prot = ing_carb = ing_fat = None
            if rec is not None:
                raw_equiv_g = w_cooked / max(0.1, rec.cooking_yield_factor)
                factor = raw_equiv_g / 100.0
                ing_kcal = round(factor * rec.calories_kcal_100g, 1)
                ing_prot = round(factor * rec.protein_g_100g, 2)
                ing_carb = round(factor * rec.carbohydrates_g_100g, 2)
                ing_fat = round(factor * rec.fat_g_100g, 2)

                total_kcal += factor * rec.calories_kcal_100g
                total_prot += factor * rec.protein_g_100g
                total_carb += factor * rec.carbohydrates_g_100g
                total_fat += factor * rec.fat_g_100g

                if rec.fiber_g_100g is not None:
                    total_fiber += factor * rec.fiber_g_100g
                    has_fiber = True
                if rec.iron_mg_100g is not None:
                    total_iron += factor * rec.iron_mg_100g
                    has_iron = True
                if rec.calcium_mg_100g is not None:
                    total_calcium += factor * rec.calcium_mg_100g
                    has_calcium = True
                if rec.potassium_mg_100g is not None:
                    total_potassium += factor * rec.potassium_mg_100g
                    has_potassium = True

                n_source = rec.source_citation
                sources_set.add(n_source)
            else:
                all_grounded = False
                n_source = "model_estimate_unverified"

            combined_conf = round((vis_conf + float(dinov3_confidence)) / 2.0, 2)
            ingredients_list.append({
                "name": ing["display_name"],
                "ingredient_key": ing["name"],
                "estimated_weight_g": w_cooked,
                "identification": ing["identification"],
                "confidence": combined_conf,
                "nutrition_source": n_source,
                "recipe_source": kb["recipe_source"],
                "calories_kcal": ing_kcal,
                "protein_g": ing_prot,
                "carbohydrates_g": ing_carb,
                "fat_g": ing_fat,
            })
            detailed_breakdown.append({
                "name": ing["name"],
                "weight_g": w_cooked,
                "identification": ing["identification"],
                "confidence": combined_conf,
                "nutrition_source": n_source,
                "recipe_source": kb["recipe_source"],
            })

        if not self.is_enabled():
            warnings.append(
                "Verified nutrition database provider is disabled; values are unverified model estimates."
            )
        if float(dinov3_confidence) < 0.65:
            warnings.append(
                f"Low classification confidence ({dinov3_confidence:.2f}); please confirm food identity before logging."
            )
        if vlm_vision_data.get("occluded_or_uncertain"):
            warnings.append("Portion or ingredients appear partially occluded; please verify serving weight.")
        if not vlm_vision_data.get("dish_matches_prediction", True):
            warnings.append("VLM noted potential visual mismatch with top classifier label; user review required.")

        nutrition_conf = round(
            min(0.95, (float(dinov3_confidence) + portion_conf_score) / 2.0 * (0.95 if all_grounded else 0.70)),
            2,
        )

        # If provider is disabled, fall back to VLM raw estimates if present or null
        if self.is_enabled() and all_grounded:
            nutrition_block = {
                "calories_kcal": round(total_kcal, 1),
                "protein_g": round(total_prot, 1),
                "carbohydrates_g": round(total_carb, 1),
                "fat_g": round(total_fat, 1),
                "fiber_g": round(total_fiber, 1) if has_fiber else None,
            }
            micronutrients_block = {
                "iron_mg": round(total_iron, 2) if has_iron else None,
                "calcium_mg": round(total_calcium, 1) if has_calcium else None,
                "potassium_mg": round(total_potassium, 1) if has_potassium else None,
            }
            provenance_status = "grounded_fctb_2013"
        else:
            raw_nutr = vlm_vision_data.get("model_estimated_nutrition") or {}
            nutrition_block = {
                "calories_kcal": round(total_kcal, 1) if total_kcal > 0 else raw_nutr.get("calories_kcal"),
                "protein_g": round(total_prot, 1) if total_prot > 0 else raw_nutr.get("protein_g"),
                "carbohydrates_g": round(total_carb, 1) if total_carb > 0 else raw_nutr.get("carbohydrates_g"),
                "fat_g": round(total_fat, 1) if total_fat > 0 else raw_nutr.get("fat_g"),
                "fiber_g": None,
            }
            micronutrients_block = {
                "iron_mg": None,
                "calcium_mg": None,
                "potassium_mg": None,
            }
            provenance_status = "model_estimate_only"

        prep_state = (
            str(vlm_vision_data.get("observed_preparation_state") or "").strip()
            or kb["preparation"]
        )
        portion_desc = kb["portion_description"]
        if fullness > 1.15:
            portion_desc = f"Large serving (~{fullness:.2f}x standard)"
        elif fullness < 0.85:
            portion_desc = f"Small serving (~{fullness:.2f}x standard)"

        requires_confirmation = (
            float(dinov3_confidence) < 0.65
            or portion_conf_label == "low"
            or bool(vlm_vision_data.get("occluded_or_uncertain", False))
            or not bool(vlm_vision_data.get("dish_matches_prediction", True))
        )

        return {
            "food_name": kb["food_name"],
            "canonical_catalog_name": kb["canonical_catalog_name"],
            "food_class": dinov3_class,
            "classification": {
                "predicted_label": dinov3_class,
                "confidence": round(float(dinov3_confidence), 4),
            },
            "portion": {
                "estimated_weight_g": est_serving_g,
                "portion_description": portion_desc,
                "weight_range_g": weight_range_g,
                "fullness_multiplier": round(fullness, 2),
                "is_approximate": True,
            },
            "ingredients": ingredients_list,
            "ingredient_breakdown": detailed_breakdown,
            "nutrition": nutrition_block,
            "micronutrients": micronutrients_block,
            "confidence": {
                "food_identification": round(float(dinov3_confidence), 4),
                "portion_estimation": round(portion_conf_score, 2),
                "nutrition_estimation": nutrition_conf,
            },
            "provenance": {
                "status": provenance_status,
                "is_verified_database": self.is_enabled() and all_grounded,
                "is_approximate": True,
                "sources": sorted(sources_set),
                "vlm_raw_estimates": vlm_vision_data,
            },
            "observed_preparation_state": prep_state,
            "occluded_or_uncertain": bool(vlm_vision_data.get("occluded_or_uncertain", False)),
            "requires_user_confirmation": requires_confirmation,
            "warnings": warnings,
            "explanation": (
                f"Approximate nutritional composition for {kb['food_name']} ({est_serving_g} g) "
                f"calculated from VLM ingredient & portion analysis grounded in FCTB 2013 food composition data."
                if (self.is_enabled() and all_grounded)
                else f"Estimated nutritional composition based on the visible meal and predicted food identity ({kb['food_name']})."
            ),
        }
