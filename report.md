# MealSense Implementation Status Report

**Date:** 2026-11-14  
**Scope:** Summary of implemented modules, AI/ML pipelines, frontend features, and remaining gaps observed across the repository.

---

## 1. Architecture Summary

MealSense is structured as a decoupled full-stack application with offline-capable local AI inference:

- **Backend (`backend/`):** Python / Django + Django REST Framework (`/api/v1/`) using SQLite locally (PostgreSQL-ready via `DATABASE_URL`).
- **Frontend (`frontend/`):** React 19, TypeScript, Vite, Tailwind CSS v4, Framer Motion, Three.js, and `vite-plugin-pwa`.
- **ML / VLM Pipeline (`ml_models/`, `dinov3_integration/`, `qwen_vlm_integration/`):** Local PyTorch / Transformers / PEFT inference combining dish classification, VLM visual attribute extraction, and FCTB 2013 nutrition grounding.
- **Dataset Tooling (`scrapper/`):** Standalone Python pipeline for scraping Facebook Group food images and filtering non-food media with TinyCLIP.

---

## 2. Current Implementation Status

### Backend (`backend/core/`, `backend/config/`)
- **Authentication & Accounts:** Custom `User` model (`email` + `username` login), CSRF/session-cookie auth (`/auth/csrf/`, `/auth/register/`, `/auth/login/`, `/auth/logout/`), `Profile` management (timezone, units, phone, gender, date of birth, height/weight, daily calorie & macro goals), profile picture upload, and account deletion with queued media cleanup (`MediaDeletionJob`).
- **Traceable Nutrition & Food Catalog:** `Food`, `FoodAlias` (English/Bengali regional aliases), `FoodServing`, `NutritionSource`, immutable active `NutritionRecord` versioning, and `FoodNutrition`. Migration `0010_seed_banglafoodnet_catalog.py` seeds 19 Bangladeshi food entries (with nutrition pending until verified).
- **Meal Logging & Goals:** `Meal` and `MealItem` (storing nutrient and source snapshots at log time), `IdempotencyRecord` for duplicate-safe meal creation, `NutritionGoal`, `NutrientTarget`, `GoalProgress`, and timezone-aware `/nutrition/daily/` and `/nutrition/weekly/` endpoints.
- **Image Storage & Recognition API:** Owner-checked private image storage/serving (`FoodImage`, `/images/<uuid>/`) and recognition endpoints (`POST /recognitions/`, `GET/POST /recognitions/<uuid>/`) supporting candidate listing, VLM analysis (`action: "analyze"`), and ingredient-level meal saving (`action: "save_meal"`).
- **Doctor Access & Sharing:** Consent-based `DoctorAccessRequest` workflow allowing unauthenticated doctors to request access via patient email/phone (`/doctor-access/request/`), patients to approve/deny/revoke in-app, and doctors to view 72-hour token-authenticated read-only meal history and analytics (`/doctor-access/view/*`) without exposing meal photos, notes, or health metrics.

### AI & Nutrition Pipeline (`ml_models/`)
- **Multi-Provider Recognition (`backend/core/services.py`):** Configurable via `AI_PROVIDER` (`dinov3`, `dinov3_vlm`, `local` BanglaFoodNet, `openai`, `gemini`, or disabled).
- **Stage 1 — Dish Classification (`ml_models/inference/classifier.py`):** Frozen `DINOv3 ViT-Small` backbone + linear classification head (`dinov3_dish_best.pth`) covering 9 Bangladeshi dishes (`bakorkhani`, `beguni`, `biriyani`, `chickpeas`, `egg_omlete`, `fuchka`, `haleem`, `hilsha_fish`, `kacchi`).
- **Stage 2 — VLM Visual Analysis (`ml_models/inference/vlm.py`):** PEFT LoRA adapter (`mealsense-vlm-lora` on `HuggingFaceTB/SmolVLM-500M-Instruct`) outputting structured JSON (`VLMVisionOutputSchema`) for dish verification, fullness multiplier, portion confidence, preparation state, and visible ingredients.
- **Stage 3 — Grounded Nutrition (`ml_models/inference/nutrition.py`):** Maps visible and recipe-inferred ingredients against **FCTB 2013** composition data and cooking yield factors so nutrient math stays deterministic outside the VLM.

### Frontend (`frontend/src/`)
- **Design System (`src/design/`):** Liquid Glass & Organic Emerald theme (`tokens.css`, `ui.tsx`, `styles.css`) supporting Light and Dark modes.
- **Hero-Only Landing Page (`src/features/landing/`):** Shown exclusively when logged out (and redirected to on logout/account deletion). Features MealSense branding, tagline, Sign in / Create account card on the left, and an interactive Three.js 3D nutrition bowl & macro-orbit scene (`MealSenseScene.tsx`) on the right.
- **Authenticated App (`src/App.tsx`, `src/components/Layout.tsx`, `src/features/`):**
  - `Overview`: Daily calorie/macro summary and recent meals.
  - `MealsPage` & `MealEditor`: Manual logging, editing/deletion, camera/photo upload, recognition candidate selection, VLM analysis, and client-side fallback lookups.
  - `Insights`: 7-day calorie and macronutrient visualizations.
  - `SharingPage` & `DoctorPortal` (`/doctor`): Patient consent management and standalone read-only doctor analytics portal.
  - `ProfilePage` & `Settings`: Profile, BMI/goal calculation, theme switching, and account deletion.
- **PWA & Offline Support (`src/lib/offline.ts`):** Installable service worker (`vite-plugin-pwa`), IndexedDB cached read snapshot, and local meal drafts.

---

## 3. Verification & Remaining Gaps

### Verified in Current Workspace
- **Frontend:** `npm run build` (`tsc -b && vite build`) and `npm run lint` (`oxlint`) pass with 0 errors and 0 warnings (with `MealSenseScene` code-split into its own chunk).
- **Backend Test Suite:** `backend/core/` contains 64 Django/ML tests across `tests.py`, `test_local_recognition.py`, `test_dinov3_recognition.py`, and `test_vlm_pipeline.py`.

### Remaining / Pending Items
- **Verified Nutrition Catalog:** Expand beyond the initial 19 seeded classes (currently marked nutrition pending) and FCTB-mapped dishes with a broader curated/licensed nutrition database.
- **Model & Dataset Governance:** Confirm dataset/model licensing and expand recognition evaluation beyond the 9 DINOv3 / 19 BanglaFoodNet classes.
- **Offline Sync Queue:** Add an offline mutation queue and conflict-resolution UI (offline support currently covers cached reads and local text drafts).
- **Production Infrastructure:** Configure managed PostgreSQL, private object storage, automated image retention policies, observability, user data export, and OpenAPI schema generation.
- **End-to-End Integration Checks:** Run live browser + Django API verification for the updated landing hero and auth redirect flow.
