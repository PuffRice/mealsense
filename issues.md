# MealSense — Major Issues Audit & Status

> Original audit generated 2026-11-14; **status verified against the working tree on
> 2026-11-15** (each issue below carries a "Status" block with fix evidence and
> remaining work). Severity: **CRITICAL** (security/legal/data-corruption),
> **MAJOR** (correctness, integrity, deploy blockers), **MODERATE**
> (quality/robustness). References to "AGENTS.md §N" point to the architectural
> contract in [`AGENTS.md`](AGENTS.md).
>
> **Note:** issues originating from the `scrapper/` module (formerly #2 — scraped
> dataset governance, #3 — scraper access-control bypass) were removed from this
> document on 2026-11-15 at the maintainer's request; the numbering below is
> renumbered accordingly, and scrapper-related items in the mixed issues (#31
> test coverage, #34 committed junk) were trimmed.
>
> **Verification baseline (2026-11-15):** backend `manage.py test core` — 74 tests
> OK (1 skipped, up from 48 at audit time); frontend `npm run build` — passes.
>
> **Overall: 20 RESOLVED · 12 PARTIALLY RESOLVED · 2 NOT RESOLVED.**

---

## Summary

| # | Severity | Area | Issue | Status |
|---|----------|------|-------|--------|
| 1 | CRITICAL | Backend/Security | Client-supplied VLM checkpoint path → arbitrary model loading (RCE risk) | ✅ RESOLVED |
| 2 | CRITICAL | Frontend/ML | Fabricated client-side nutrition table with universal 165 kcal fallback | ✅ RESOLVED |
| 3 | MAJOR | Backend | Nutrition values fabricated from labels, auto-attached to every recognition | ✅ RESOLVED |
| 4 | MAJOR | Backend | Any user auto-publishes "verified"/"approved" global catalog data | ✅ RESOLVED |
| 5 | MAJOR | Backend | Public doctor endpoint leaks account existence; token never rotated | ✅ RESOLVED |
| 6 | MAJOR | ML | "Verified FCTB 2013" values hardcoded in source with unverifiable citations | 🟡 PARTIAL |
| 7 | MAJOR | Repo hygiene | ~450 MB of ML binaries committed, incl. 3 copies of one checkpoint | 🟡 PARTIAL |
| 8 | MAJOR | Frontend | Unknown VLM nutrient values rendered as zero | ✅ RESOLVED |
| 9 | MAJOR | Backend/Config | DEBUG defaults on; no SSL/HSTS; throttles per-process (no cache) | ✅ RESOLVED |
| 10 | MAJOR | Backend | Heavy torch/VLM inference runs synchronously inside HTTP requests | 🟡 PARTIAL |
| 11 | MAJOR | ML | VLM portion estimation has zero evaluation; eval number signals overfitting | 🟡 PARTIAL |
| 12 | MAJOR | Backend | `nutrient_snapshot` falls back to unapproved version-1 records | ✅ RESOLVED |
| 13 | MAJOR | ML/Deploy | Default VLM checkpoint path points at an empty untracked directory | ✅ RESOLVED |
| 14 | MAJOR | Backend | Monolithic `core` app; sys.path hack imports package outside `backend/` | ❌ NOT RESOLVED |
| 15 | MAJOR | Frontend | No auth/session-expiry handling in API layer | 🟡 PARTIAL |
| 16 | MAJOR | Frontend | Doctor access token in `sessionStorage`; error-string state machine | ✅ RESOLVED |
| 17 | MAJOR | Backend | Duplicate phone on profile update → unhandled IntegrityError (500) | ✅ RESOLVED |
| 18 | MAJOR | Backend | Meal PATCH `version` contract bug; no FoodLog audit trail | 🟡 PARTIAL |
| 19 | MAJOR | Frontend | Timezone inconsistency: meals can land on the wrong day | ✅ RESOLVED |
| 20 | MAJOR | ML | Hardcoded serving weights, yield factors, and confidence scores | 🟡 PARTIAL |
| 21 | MAJOR | ML | Hallucination laundering: KB priors re-labeled as VLM observations | ✅ RESOLVED |
| 22 | MODERATE | ML | Two near-identical DINOv3 classifier implementations that already diverge | ✅ RESOLVED |
| 23 | MODERATE | ML | Model version tracking gaps (`'local:dinov3'` constant, no checkpoint hash) | 🟡 PARTIAL |
| 24 | MODERATE | ML | Data-mapping bugs: milk→yogurt, fuchka↔chotpoti alias collapse, substring matching | ✅ RESOLVED |
| 25 | MODERATE | Backend | Unknown-as-zero in goals and daily progress | ✅ RESOLVED |
| 26 | MODERATE | Frontend | Nutrition math duplicated client-side (per-100g engine, BMR/TDEE) | ✅ RESOLVED |
| 27 | MODERATE | Backend | Retention: `IdempotencyRecord` and uploaded images grow without bound | 🟡 PARTIAL |
| 28 | MODERATE | Frontend | Modal accessibility (no Escape, no focus trap), `window.alert/confirm/prompt` | 🟡 PARTIAL |
| 29 | MODERATE | Frontend | Meal photo upload: no size gate, no abort, stale-response race | ✅ RESOLVED |
| 30 | MODERATE | Frontend | tsconfig `strict` not enabled; zero frontend tests; minimal lint | 🟡 PARTIAL |
| 31 | MODERATE | Testing | Untested high-risk paths (backend services, VLM fallback) | 🟡 PARTIAL |
| 32 | MODERATE | Secret handling | Live Gemini API key in plaintext workspace `.env` | ✅ RESOLVED |
| 33 | MODERATE | Frontend | Monolithic components (1,112-line MealEditor; 3,711-line styles.css); dead code | 🟡 PARTIAL |
| 34 | MODERATE | Misc | Committed junk: `tmp/`, `output/pdf/` | ✅ RESOLVED |

---

## CRITICAL

### 1. Client-controlled VLM checkpoint path → arbitrary local model loading (potential RCE)

- **Where (audit):** `backend/core/views.py:479-485` read
  `request.data.get('checkpoint')` and passed it straight to
  `analyze_food_image(...)`; `ml_models/inference/config.py:82-110` treated the
  string as an arbitrary filesystem path (absolute paths accepted), loaded via
  `PeftModel.from_pretrained` (`vlm.py:305-311`). An authenticated user could
  point the server at a crafted adapter → `torch.load` fallback → RCE, plus
  filesystem probing and multi-GB model loads (DoS).
- **Contract:** AGENTS.md §12 (validate all user-controlled input).

> **Status (2026-11-15): ✅ RESOLVED.** Raw request pass-through removed.
> `backend/core/views.py:470` → `validate_vlm_checkpoint_name(request.data.get('checkpoint'))`;
> `backend/core/services.py:301-313` validates against the checkpoint names in
> `model_config.yaml` (safe fallback set if config loading fails).
> `ml_models/inference/config.py:89-92` also rejects unknown checkpoint targets;
> `resolve_project_path` is now only used for config-declared paths. Device is
> server-side only (`views.py:471`). Regression test:
> `backend/core/tests.py:873` (`test_recognition_detail_rejects_untrusted_checkpoint_parameter`
> posts `'/tmp/evil_checkpoint'`, expects 400).

### 2. Fabricated client-side nutrition table with universal 165 kcal fallback

- **Where (audit):** `frontend/src/features/meals/MealEditor.tsx:48-104` —
  `FCTB_FALLBACK_PER_100G` hardcoded table with a catch-all
  `{ portion_g: 150, kcal_100g: "165.0", ... }` for any unrecognized food;
  fuzzy substring matching; values flowed into `foodsApi.create` and persisted
  as catalog `Food` records.
- **Contract:** AGENTS.md §1 ("AI identifies; the nutrition domain
  calculates"; "unknown is not zero"), ADR-004/ADR-008.

> **Status (2026-11-15): ✅ RESOLVED.** The fallback table, the 165 kcal
> catch-all, and the fuzzy matching are gone. Unknown foods open the Add Food
> form pre-filled for user review; the form requires **all** per-100 g values
> from the user before `foodsApi.create` (`MealEditor.tsx:364-371`); foods
> without nutrition render "Nutrition pending" (`:818-820`, `:1077-1078`);
> provenance labeled "user reviewed" (`:382`).

---

## MAJOR

### 3. Nutrition values fabricated from labels and auto-attached to every recognition

- **Where (audit):** `backend/core/services.py:211-239` —
  `_attach_candidate_nutrition()` ran for every completed recognition with
  `conf = float(cand.get('confidence', 0.8))` (fabricated default) and
  `estimate_for_any_label(...)` producing invented servings
  (`nutrition.py:415-437`: `serving_g = 150.0`, fake confidence
  `"portion_estimation": 0.72`) computed without the VLM looking at the image.
- **Contract:** AGENTS.md §10, §1, ADR-008.

> **Status (2026-11-15): ✅ RESOLVED.** Rewritten to attach only an
> already-validated VLM analysis to the top candidate with no fabrication
> (`services.py:212-220`: "…without fabricating estimates for unanalyzed
> labels"). Default confidence is 0, not 0.8, clamped in `normalize_candidates`
> (`services.py:99`). `estimate_for_any_label` now returns a per-100 g
> reference basis with `estimated_weight_g: None` and a "portion weight was
> not visually estimated" warning (`nutrition.py:431-436,489`).

### 4. Any user auto-publishes "verified"/"approved" global catalog data

- **Where (audit):** `backend/core/services.py:320-388` — inside a user's
  save-meal transaction, `ensure_analyzed_catalog_foods()` created global
  `Food` rows (`created_by=None, is_verified=True`) and
  `NutritionRecord(verification_status='approved')` with no review; no unique
  constraint on `Food.name` either.
- **Contract:** AGENTS.md §11/ADR-004; §9.7.

> **Status (2026-11-15): ✅ RESOLVED.** Foods are now user-scoped and
> explicitly untrusted: `Food.objects.get_or_create(created_by=user, ...,
> is_verified=False)` (`services.py:342-355`); records created with
> `verification_status='user_supplied'` (`:382`); source created with
> `is_trusted: False` (`:327`). Unique constraint on shared catalog names:
> `models.py:136-141` (`unique_shared_catalog_food_name`, condition
> `created_by__isnull=True`), in migration 0012.

### 5. Public doctor endpoint leaks account existence; token never rotated on revoke

- **Where (audit):** `backend/core/views.py:586-590` returned `token: None`
  for unmatched identifiers vs a real 43-char token for matched ones —
  contradicting the class docstring's anti-enumeration claim.
  `services.py:783-813` — `decide_doctor_access_request()` never rotated
  `view_token` on revoke→re-approve; non-constant-time comparison.
- **Contract:** AGENTS.md §12.

> **Status (2026-11-15): ✅ RESOLVED.**
> - Enumeration leak **fixed**: unmatched identifiers now receive a random
>   opaque token with an identical generic 202 body
>   (`views.py:575-581`, `services.py:819-824`); test
>   `tests.py:637` asserts identical messages and token length ≥ 32.
> - Constant-time compare **fixed**: `secrets.compare_digest` (`services.py:885`).
> - Token rotation **fixed**: `decide_doctor_access_request`
>   (`services.py:1049-1073`) rotates `view_token` whenever a revoked request
>   is approved again (`services.py:1058,1064-1070`) — the token the doctor
>   received while the share was active is invalidated, so a leaked copy
>   cannot be resurrected by re-approval; the doctor regains access through a
>   fresh request, whose creation response carries the new token.
>   `test_revoke_then_reapprove_rotates_token` (`tests.py:828`) asserts the
>   token changed and the old token returns 404 after renewal. Expiry-window
>   renewal (no revocation) deliberately keeps the same token.

### 6. "Verified FCTB 2013" nutrition values hardcoded in source with unverifiable citations

- **Where (audit):** `ml_models/inference/nutrition.py:34-63` — "Verified FCTB
  2013" values with unverifiable codes embedded in code; generic FAO PDF URL
  cited as `recipe_source` for all nine dishes (L18-20, 168, 182, 196, ...);
  invented ingredient priors with fabricated confidence numbers (L171-175).
- **Contract:** AGENTS.md §9.8, §11, ADR-004.

> **Status (2026-11-15): 🟡 PARTIALLY RESOLVED.**
> - Fixed (earlier): generic FAO URL replaced with an explicitly unverified
>   label (`"MealSense Traditional Bangladeshi Recipe Composition Prior
>   (unverified reference; requires user confirmation)"`,
>   `nutrition.py:18-20`); per-record `source_citation`; every output carries
>   `provenance.status`
>   (`"unverified_reference"` / `"fctb_2013_grounded_with_unverified_recipe_priors"`
>   / `"model_estimate_only"`, L659-663, 713-719), `is_verified_database: False`,
>   `requires_user_confirmation: True`, and explicit warnings (L628-643);
>   priors tagged `identification: "visible" | "recipe_inferred"` instead of
>   posing as observations.
> - Fixed (2026-11-15): the runtime source of composition records is now the
>   SQLite database `ml_models/data/fctb_2013_nutrition.db` (24 rows,
>   materialized by the new committed script
>   `ml_models/scripts/build_fctb2013_db.py`). Each row carries provenance
>   metadata (`source_name`, `source_citation`, `basis`, `license_note`,
>   `retrieved_at`) and a CHECK-constrained `verification_status` column
>   (default `unverified`); a `db_metadata` table records the source,
>   reference, basis, license note, and build time. The provider reads the
>   database first (`nutrition.py:356-367` `lookup` → `:369-400`
>   `_lookup_db`, now mapping fiber/iron/calcium/potassium columns) and the
>   in-code table is demoted to a documented fallback for clones where the
>   DB has not been built. Misleading "Verified" naming removed: header
>   comment states values are ATTRIBUTED but NOT independently verified
>   (`nutrition.py:34-39`), `VerifiedIngredientRecord` renamed to
>   `FctbIngredientRecord` (`:313`), provider docstring and the
>   "Verified nutrition database" warning rewritten (`:337-354`, `:646`).
> - **Remaining:** the values themselves still need independent verification
>   against the actual *Food Composition Table for Bangladesh, 2013*
>   publication (INFS, University of Dhaka) — the FCTB codes cannot be
>   confirmed offline — and the publication's license/redistribution terms
>   are unconfirmed (`license_note` in the DB). Coverage is also small
>   (24 ingredient rows). After review, flip row
>   `verification_status` to `reviewed`/`approved` in the DB — never in code.

### 7. ~450 MB of ML binaries committed to git, including 3 copies of one checkpoint

- **Where (audit):** git-tracked: `backend/ml_models/dinov3/checkpoint.pth`
  (86.5 MB), `dinov3_integration/dinov3_dish_best.pth` (86.5 MB),
  `dinov3_integration/meal_classifier_dinov3.zip` (80.3 MB),
  `dinov3_integration/dinov3_offline_model/model.safetensors` (86.4 MB,
  Meta non-commercial DINOv3 license, redistribution unconfirmed),
  `qwen_vlm_integration/.../adapter_model.safetensors` (38.3 MB) + an identical
  copy under `checkpoint-147/` + trainer internals (`optimizer.pt` 77 MB, etc.).

> **Status (2026-11-15): 🟡 PARTIALLY RESOLVED.**
> - All listed binaries are now **untracked** (staged deletions); `.gitignore`
>   adds `backend/ml_models/dinov3/*.pth` and the
>   `qwen_vlm_integration/*/*/{rng_state.pth,scheduler.pt,training_args.bin}`
>   patterns. Only text files remain tracked in `checkpoint-147/`.
> - **Remaining:** deletions are staged, **not committed** — HEAD (`3b54f10`)
>   and history (added in `2f4502b`) still contain every blob. To actually
>   shrink the repo and remove the redistribution exposure: commit the
>   deletions, then decide on history rewriting (git filter-repo) / LFS.

### 8. Unknown VLM nutrient values rendered as zero in the UI

- **Where (audit):** `frontend/src/features/meals/MealEditor.tsx:968-979` —
  `?? 0` coercions rendered unknown macros as `0g`; `?? "0"` fed the
  custom-food form (L372-374).
- **Contract:** AGENTS.md §1 ("unknown is not zero").

> **Status (2026-11-15): ✅ RESOLVED.** VLM banner renders `—` for missing
> macros (`MealEditor.tsx:966-968`); `toPer100g` returns `""` for
> null/undefined/NaN (`:310-318`); custom-food form uses empty strings for
> nulls (`:333-351`). Only remaining `?? 0` uses are a non-nutrition badge
> check (`Layout.tsx:93,252`).

### 9. Production security settings gaps; rate limiting is per-process

- **Where (audit):** `backend/config/settings.py:16-17` — DEBUG defaulted **on**
  (`'Django_DEBUG'` default `'1'`); no `SECURE_SSL_REDIRECT`/HSTS/
  `SECURE_PROXY_SSL_HEADER` (`manage.py check --deploy` → W004/W008); no
  `CACHES` setting so DRF throttle counters were per-process LocMemCache;
  `doctor_view: 1200/hour` on token-gated medical-history endpoints.

> **Status (2026-11-15): ✅ RESOLVED (one caveat).**
> - `settings.py:17`: `DEBUG = os.environ.get('DJANGO_DEBUG', '0') == '1'`
>   (default off); dev `SECRET_KEY` refused when not DEBUG (L18-19).
> - Non-DEBUG non-test: `SECURE_SSL_REDIRECT`, `SECURE_HSTS_SECONDS` (default
>   31536000) + INCLUDE_SUBDOMAINS + PRELOAD, `SECURE_PROXY_SSL_HEADER`
>   (`settings.py:80-85`).
> - `CACHES` now configurable via `DJANGO_CACHE_BACKEND`/`DJANGO_CACHE_LOCATION`
>   (`settings.py:87-95`); `doctor_view` reduced 1200 → **120/hour**
>   (`settings.py:123`).
> - **Caveat:** the default backend is still LocMemCache (per-process) unless
>   the env points at a shared cache — production deployments must set
>   `DJANGO_CACHE_BACKEND` to Redis/DB cache for reliable multi-worker limits.

### 10. Heavy torch/VLM inference runs synchronously inside HTTP requests

- **Where (audit):** `backend/core/views.py:409` (`recognize_with_provider`)
  and `views.py:485-491` (`analyze_food_image`) ran in-request — first request
  loads an 86 MB checkpoint + ViT backbone and the VLM path generates up to
  256 tokens on CPU, blocking a worker thread for tens of seconds. Also
  `views.py:385` globally mutated `Image.MAX_IMAGE_PIXELS = 20_000_000`,
  weakening PIL's decompression-bomb guard process-wide.
- **Contract:** AGENTS.md §7 (Tasks layer), §8.

> **Status (2026-11-15): 🟡 PARTIALLY RESOLVED.**
> - Fixed: global `MAX_IMAGE_PIXELS` mutation removed; replaced by a
>   per-request guard — format allowlist (JPEG/PNG/WEBP) + 20 MP cap raising
>   `ValueError` → 400 (`views.py:381-386`), with `DecompressionBombError`
>   caught; a configurable limit also exists in `ml_models/inference/config.py:75`.
> - **Remaining:** inference is still synchronous inside request handlers
>   (`views.py:400`, `views.py:476-482`); no threads/task queue/celery exists
>   (only a `Lock` around model loading). Long-running recognitions still
>   block worker threads.

### 11. VLM portion estimation has zero evaluation; the only eval number signals overfitting

- **Where (audit):** `checkpoint-147/trainer_state.json` — eval_loss ≈
  training loss ≈ 0.0054 on ≈63 samples (memorization); `ml_models/README.md`
  cited the val loss as "best model" evidence with no portion/ingredient
  metrics; `visual_fullness_multiplier` (0.25–3.0) was the sole portion
  signal with no ground truth or calibration.
- **Contract:** AGENTS.md §10/§16.

> **Status (2026-11-15): 🟡 PARTIALLY RESOLVED.**
> - Fixed: `ml_models/README.md:43` now states explicitly that the eval loss
>   "is **not** a calibrated benchmark of portion-weight accuracy (MAE/MAPE)
>   or ingredient-recall F1 on an independent held-out test set" and that
>   portion weights/recipe-inferred ratios "are approximate proposals that
>   require user confirmation."
> - `vlm.py:45` keeps `visual_fullness_multiplier` but pairs it with an
>   explicit `portion_confidence` field (L46); `nutrition.py:507-512` maps it
>   to a score only when VLM data exists (else `portion_estimation: None`,
>   L710).
> - **Remaining:** no new evaluation artifacts or metrics exist (no held-out
>   split, no portion MAE, no ingredient F1). The claim correction is honest,
>   but the missing evaluation itself remains.

### 12. `nutrient_snapshot` silently uses unapproved version-1 records

- **Where (audit):** `backend/core/services.py:486-494` — fallback filtered
  `NutritionRecord.objects.filter(food=food, version=1)` regardless of
  `verification_status`; migration 0006 backfilled `unverified` records, so an
  imported draft v1 record silently changed what users log.
- **Contract:** ADR-004.

> **Status (2026-11-15): ✅ RESOLVED.** Primary path is `FoodNutrition.active_record`,
> which `FoodNutrition.clean()` enforces is `'approved'` only
> (`models.py:215-216`); the bare fallback now filters
> `verification_status='approved'` (`services.py:490`); user-created foods use
> `'user_supplied'` (`services.py:487`). Tests:
> `tests.py:154` (`test_unapproved_nutrition_revision_does_not_change_logged_amount`),
> `tests.py:180` (`test_active_nutrition_must_match_food_and_be_approved`).

### 13. Default VLM checkpoint path points at an empty, untracked directory

- **Where (audit):** `ml_models/configs/model_config.yaml:23-24` pointed
  `mealsense-vlm-lora` at the empty `ml_models/checkpoints/mealsense-vlm-lora/`
  while the working adapter lived in `qwen_vlm_integration/`; the nutrition DB
  and test assets referenced `D:\CS\Hackathon\Mealsense_Models` outside the repo.

> **Status (2026-11-15): ✅ RESOLVED.** `model_config.yaml:24` now points to
> `"qwen_vlm_integration/mealsense-vlm-lora"` (verified `adapter_config.json`
> exists there; `checkpoint-147` also resolves). Nutrition DB is repo-relative
> (`ml_models/data/fctb_2013_nutrition.db`, `config.py:124,229-231`); the file
> now exists, built with provenance metadata, and the provider reads it first
> (see issue 6); the out-of-repo path is gone.

### 14. Monolithic `core` app; backend depends on a sibling package via sys.path hack

- **Where (audit):** `backend/core/models.py` (373 lines) holds all eight
  domain modules in one app; `backend/config/settings.py:9-10` inserts
  `PROJECT_ROOT` (the repo root) into `sys.path` so the backend can import
  `ml_models.inference.*` from outside `backend/` — deploying `backend/` alone
  degrades every recognition endpoint to `LOCAL_DEPENDENCIES_MISSING`/500.
  No `FoodLog` audit model, no `DailyNutritionSummary`.
- **Contract:** AGENTS.md §3 (eight modules), §7.

> **Status (2026-11-15): ❌ NOT RESOLVED.**
> - `settings.py:9-10` sys.path hack unchanged, no explanatory comment.
> - `ml_models` package still lives at the repo root and is imported by the
>   backend (`views.py:473`, `services.py:230,253,307,318`); `backend/ml_models/`
>   holds only data/weights, not the package.
> - Partial mitigations elsewhere: a `FoodLog` audit model **and** a
>   `DailyNutritionSummary` model now exist (migration `0012_dailynutritionsummary_foodlog_modelversion_and_more.py`),
>   and `ModelVersion` was added — so the missing-models part of this issue is
>   addressed, but the packaging/architecture problem is untouched. `backend/`
>   alone remains non-deployable for recognition.

### 15. No auth/session-expiry handling in the frontend API layer

- **Where (audit):** `frontend/src/lib/api.ts:23-53` — no 401 handling, no
  timeout/`AbortController`, error extraction `Object.values(data)[0]`, no
  retry; `mealsApi.list()` / `foodsApi.list()` returned all rows unpaginated
  with client-side filtering (`MealsPage.tsx:30-36`, `MealEditor.tsx:276-282`).

> **Status (2026-11-15): 🟡 PARTIALLY RESOLVED.**
> - Fixed: non-auth 401s dispatch `mealsense:unauthorized`; App listens and
>   resets auth state (`api.ts:76-84`, `App.tsx:68-83`). All requests use a
>   30 s `AbortController` timeout with a network-failure `ApiError`
>   (`api.ts:58-72`). Error extraction is recursive and prefers `error`/`detail`
>   (api.ts:35-38) — still first-value based, though.
> - **Remaining:** no retry logic; `mealsApi.list()` / `foodsApi.list()` are
>   still unpaginated (`api.ts:142,152`) and `MealsPage.tsx:30-36` still
>   filters all meals in memory. (DoctorPortal got server-side pagination —
>   see issue 33 — but the patient-facing lists did not.)

### 16. Doctor access token persisted in `sessionStorage`; error-string state machine

- **Where (audit):** `frontend/src/features/doctor/DoctorPortal.tsx` stored the
  bearer-equivalent token in `sessionStorage` (XSS-readable), detected access
  state by matching the error string `"not active"`, and cleared the token on
  any error including transient network failures.

> **Status (2026-11-15): ✅ RESOLVED.** No `sessionStorage`/`TOKEN_KEY` remains
> (grep-clean); token is React state only (`DoctorPortal.tsx:63`) with explicit
> `forget()` (`:204-212`). State machine is status-code based: only
> `ApiError.status === 403 || 404` triggers "blocked" (`:121-124`); other
> failures keep the data and show a Retry button (`:126-127`, `:554-560`).
> (Server-side token rotation on revoke→re-approve is now implemented — see
> issue 5.)

### 17. Duplicate phone on profile update → unhandled IntegrityError (HTTP 500)

- **Where (audit):** `backend/core/serializers.py:44-49` normalized but never
  checked phone uniqueness; `PATCH /api/v1/users/me/` with a claimed phone →
  `IntegrityError` → 500. No test.

> **Status (2026-11-15): ✅ RESOLVED.** `validate_phone` performs scoped
> uniqueness validation excluding the current instance (`serializers.py:44-55`);
> `views.py:181-182` catches `IntegrityError` → 400 field error as a safety
> net. Tests: `tests.py:836` (`test_duplicate_phone_returns_400_instead_of_500`),
> `tests.py:824` (`test_profile_phone_saved_and_clearable`).

### 18. Meal PATCH `version` contract bug; no FoodLog audit trail

- **Where (audit):** `version` was `required=False` in `MealInputSerializer`
  but omitting it always yielded 409 (`views.py:296-306`,
  `services.py`); `replace_meal_items()` deleted and re-created items with no
  audit events (ADR-006, AGENTS.md §8 unimplemented).

> **Status (2026-11-15): 🟡 PARTIALLY RESOLVED.**
> - Fixed (added differently): new `FoodLog` audit model
>   (`models.py:475-487`, migration 0012) with audit events on create
>   (`services.py:645`), update with previous+new value snapshots (`:665`),
>   and delete with `meal_id_snapshot` surviving deletion via `SET_NULL`
>   (`:678`); test `tests.py:847` asserts created/deleted rows. Item-level
>   changes are captured in meal-level snapshots.
> - **Remaining:** the version contract bug is unchanged —
>   `serializers.py:184` still declares `version` `required=False`, but
>   `services.py:654` still 409s whenever `data.get('version') != meal.version`,
>   so omitting `version` always fails despite the serializer contract.

### 19. Timezone inconsistency: meals can land on the wrong day

- **Where (audit):** `frontend/src/features/profile/bmi.ts:9-11` used
  `toISOString().slice(0,10)` (UTC date); `MealEditor.tsx` used the device
  offset while `App.tsx:dateInZone` used the profile timezone — meals could
  be queried on the wrong day.
- **Contract:** AGENTS.md §4.5.

> **Status (2026-11-15): ✅ RESOLVED (minor residue).** `getTodayIso(timeZone?)`
> uses `Intl.DateTimeFormat` with the profile timezone
> (`bmi.ts:9-27`); `localDateTime(date, timeZone)` uses the same pattern with a
> device-offset fallback only for invalid zones (`MealEditor.tsx:33-58`);
> `MealEditor` receives `timezone={user.profile.timezone}` (`App.tsx:440`).
> Minor residue: `ProfilePage.tsx:55` calls `getTodayIso()` without a timezone
> argument (device-local date) — not a UTC-vs-local bug.

### 20. Hardcoded serving weights, yield factors, and confidence scores with no evidence

- **Where (audit):** `ml_models/inference/nutrition.py` — invented
  `standard_serving_g` per dish (L166-303), fixed `serving_g = 150.0` for any
  ingredient lookup (L415-437), ±15% weight ranges from nothing (L512-513),
  and a "numerology" confidence formula mixing unrelated quantities
  (L639-642, 603); backend fabricated missing confidence as 0.8.
- **Contract:** AGENTS.md §4.2, §10.

> **Status (2026-11-15): 🟡 PARTIALLY RESOLVED (largely addressed).**
> - Fixed: the fixed `serving_g=150` per-ingredient estimate is gone —
>   `estimate_for_any_label` returns a per-100 g basis with
>   `estimated_weight_g: None` and an explicit warning
>   (`nutrition.py:431-436,489`). The numerology confidence formula is gone:
>   `portion_estimation` is a documented mapping from the VLM's
>   `portion_confidence` label (L508-511) or `None`; `nutrition_estimation`
>   is always `None` (L711). No default-0.8 confidence remains in backend
>   services. Every result is `is_approximate: True` +
>   `requires_user_confirmation: True` (L687-703).
> - **Remaining:** dish `standard_serving_g` values are still hardcoded
>   (L166-303) — now labeled with `portion_description` and `is_approximate`,
>   but still invented; the flat ±15% `weight_range_g` fabrication remains
>   (L515), labeled only as approximate rather than as an explicit assumption.

### 21. Hallucination laundering: KB priors re-labeled as VLM observations

- **Where (audit):** `ml_models/inference/vlm.py:482-499` — the malformed-JSON
  fallback constructed "visible ingredients" with confidence values from
  `NINE_CLASS_KNOWLEDGE_BASE`, indistinguishable from real VLM output.

> **Status (2026-11-15): ✅ RESOLVED.** The fallback now returns
> `visible_ingredients=[]`, `portion_confidence="low"`,
> `occluded_or_uncertain=True` — no KB priors injected (`vlm.py:482-491`).
> `nutrition.py` then marks ingredients `recipe_inferred` with
> `confidence: None` and warns "VLM visual analysis was not run; ingredient
> shares and portion weight are unverified recipe priors" (L536-539, 636-639);
> `vlm.py:511-515` appends the JSON-recovery notice and forces user
> confirmation.

---

## MODERATE

### 22. Two near-identical DINOv3 classifier implementations that already diverge

- **Where (audit):** `backend/core/dinov3_recognition.py:48-70` duplicated
  `ml_models/inference/classifier.py:114-148` (~100 lines, same
  architecture/transform/validation) with subtle divergences.

> **Status (2026-11-15): ✅ RESOLVED.** `backend/core/dinov3_recognition.py:11`
> imports `_load_cached_classifier` and `get_checkpoint_sha256_tag` from
> `ml_models.inference.classifier` and delegates model loading (L33-43) —
> loading logic is single-sourced. Residual duplication is only image
> open/validation and top-k selection in `predict_food` (L46-75).

### 23. Model version tracking gaps

- **Where (audit):** `'model_version': 'local:dinov3'` was a constant
  (`dinov3_recognition.py:117`); `classifier.classify()` returned no
  checkpoint identity; no `ModelVersion` records existed.
- **Contract:** AGENTS.md §10, ADR-007.

> **Status (2026-11-15): 🟡 PARTIALLY RESOLVED.**
> - Fixed: checkpoint identity is derived — `get_checkpoint_sha256_tag`
>   (16-char SHA-256 of the artifact, `classifier.py:27-37`) feeds
>   `model_version: f"local:dinov3:{ckpt_tag}"` (`classifier.py:290-295`) and
>   `recognize_dinov3` (`dinov3_recognition.py:90-91`). The constant remains
>   only as the untracked-checkpoint fallback.
> - **Remaining:** a `ModelVersion` model exists (`models.py:462`) but is
>   never created or queried — no DB records are written; no metrics
>   artifacts for either checkpoint (README prose only).

### 24. Data-mapping bugs in the nutrition provider

- **Where (audit):** `nutrition.py:110-111` mapped `"milk": "yogurt"`;
  fuchka aliased to pani puri (`recognition_labels.py:9`, `nutrition.py:151`);
  substring matching in `resolve_dish_class` forced unsupported foods into a
  9-class profile instead of unknown.

> **Status (2026-11-15): ✅ RESOLVED.** `"milk": "cow_milk"`
> (`nutrition.py:112`); fuchka aliases are `('Fuchka', 'phuchka')` with no pani
> puri collapse (`recognition_labels.py:9`, `nutrition.py:150-151`);
> `resolve_dish_class` (L385-391) is exact-match only and returns `None` →
> unknown outcome, treated as "no grounding" rather than forcing the nearest
> dish.

### 25. Unknown-as-zero in goals and daily progress

- **Where (audit):** `backend/core/services.py:619` —
  `int(targets.get(nutrient, 0))`; `backend/core/views.py:346` —
  `Decimal(daily_totals.get(target.nutrient_name, '0'))` — untracked
  nutrients reported as 0, not unknown.
- **Contract:** AGENTS.md §1.

> **Status (2026-11-15): ✅ RESOLVED.** Missing targets yield `None`
> (`services.py:718`); unknown actuals are `None` in the progress payload
> (`views.py:337-338`).

### 26. Nutrition math duplicated client-side

- **Where (audit):** `MealEditor.tsx` computed per-100 g and totals
  client-side (`estimate`, `toPer100g` — which could divide by the fabricated
  fallback weight — and `customPortionTotalKcal`); a full BMR/TDEE/macros
  calculator in `frontend/src/features/profile/bmi.ts:58-144` applied to goals
  client-side.
- **Contract:** ADR-008/ADR-012, §9.6/§9.8.

> **Status (2026-11-15): ✅ RESOLVED.** All authoritative nutrition math moved
> behind server endpoints.
> - **Server nutrition preview:** `POST /api/v1/nutrition/preview/`
>   (`backend/core/urls.py:16`, `views.py:335-342`) computes per-item and
>   meal-total values with Decimal + provenance-aware lookup mirroring
>   `nutrient_snapshot` (`services.py:519-541` `catalog_per_100g_values`,
>   `:543-590` `compute_nutrition_preview`). Unknown nutrients propagate as
>   `None` totals, never zero, with a `pending` flag. Items accept either
>   `{food_id, grams}` or inline per-100 g values
>   (`serializers.py:100-125`); other users' foods are rejected (`views.py`
>   filter `Q(created_by=user) | Q(created_by__isnull=True)`, `is_active=True`).
> - **Server goal suggestions:** `POST /api/v1/goals/suggestions/`
>   (`urls.py:18`, `views.py:344-374`) does BMI + Mifflin-St Jeor BMR/TDEE +
>   macro splits with identical rounding/clamps (`services.py:592-640`
>   `compute_goal_suggestions`), accepting optional height/weight/gender/dob
>   overrides that fall back to the saved Profile per field
>   (`serializers.py:127-141`); returns `suggestion: null` when inputs are
>   insufficient; range validation → 400.
> - **Server per-100 g derivation for VLM analyses:** the three analysis
>   payload sites now attach server-derived `nutrition_per_100g`
>   (`views.py:327-333` `analysis_with_per_100g` applied in `RecognitionView`
>   and `RecognitionDetailView`; `services.py:642-668`
>   `per_100g_from_analysis`, quantized to 0.1 with ROUND_HALF_UP).
> - **Client math removed:** `MealEditor.tsx` no longer computes per-100 g or
>   totals — the client `estimate`/`toPer100g`/`customPortionTotalKcal` math is
>   deleted; per-item rows, the footer total, and "Nutrition pending" now come
>   from a debounced 280 ms sequence-guarded preview call
>   (`MealEditor.tsx:258-286`, `:294-302`, `:866`, footer `:1083-1099`);
>   `populateFormWithAnalysis` consumes `nutrition_per_100g` directly
>   (`:341-352`). `bmi.ts` now contains only date/age display helpers —
>   `computeBmiAndSuggestions`/`BmiSuggestion` are deleted
>   (`bmi.ts:1-62`); `ProfilePage.tsx` fetches the server suggestion
>   (debounced 300 ms, `ProfilePage.tsx:55-90`) and renders
>   `suggestion.healthy_min_kg/healthy_max_kg` strings. New API clients:
>   `api.ts:160-172` (`nutritionApi.preview`, `goalsApi.suggestions`);
>   types in `types.ts:98-102,121-164`.
> - **Tests:** `tests.py:323-390` — Decimal math parity (130×150/100 =
>   195.00), inline values, unknown-nutrient `None` totals, cross-user food
>   400, exact suggestion values (male 25y default: 2190 kcal/104/291/68),
>   null-when-insufficient, out-of-range 400. Suite: 74 tests OK.
> - **Rounding note:** client JS `Math.round` ≡ Python `ROUND_HALF_UP` for the
>   positive values involved, so previously displayed numbers do not change.

### 27. Retention: `IdempotencyRecord` and uploaded images grow without bound

- **Where (audit):** `IdempotencyRecord` had no TTL/cleanup (`models.py:342-351`);
  uploaded meal images persisted before recognition were kept even on failure
  (`views.py:406-408`).
- **Contract:** AGENTS.md §12.

> **Status (2026-11-15): 🟡 PARTIALLY RESOLVED.**
> - Fixed: `prune_expired_records(idempotency_days=7, orphan_image_hours=24)`
>   (`services.py:685-701`) deletes expired idempotency rows and orphan
>   images (unattached > 24 h); wired into the
>   `retry_media_deletions` management command (`:15`).
> - **Remaining:** images attached to a **failed** recognition are retained
>   forever — the orphan filter requires `foodprediction__isnull=True`
>   (`services.py:693-694`) and `RecognitionView` always creates a
>   `FoodPrediction` row even for `failed`/`unavailable` statuses
>   (`views.py:402-406`), so those images are never orphans and never pruned.

### 28. Frontend accessibility and native-dialog antipatterns

- **Where (audit):** `GlassModal` had no Escape handling, no focus trap, no
  focus restore (`ui.tsx:166-204`); App.tsx used `window.alert/confirm/prompt`
  for logout, meal deletion, and account deletion incl. password entry.

> **Status (2026-11-15): 🟡 PARTIALLY RESOLVED.**
> - Fixed: GlassModal now handles Escape (`ui.tsx:186-239`), sets initial
>   focus, traps Tab with wrap-around (`:216-228`), and restores focus on
>   unmount (`:233-237`). App.tsx: delete-meal and account-deletion
>   confirmations (with password `Field`) are GlassModals
>   (`App.tsx:450-497`, `:499-552`); notices use `ToastNotice`
>   (`:46-49,329-335`; `ui.tsx:404-426`).
> - **Remaining:** `Layout.tsx:212` still uses `window.alert` for the
>   About/help message; `SharingPage.tsx:77,84` still use `window.confirm`
>   for approve/revoke decisions.

### 29. Meal photo upload: no size gate, no abort, stale-response race

- **Where (audit):** `MealEditor.tsx:445-488` — no size/type gate (unlike the
  avatar's 5 MB check), no abort, no sequence guard so a slow earlier upload
  could attach the wrong image; no timeout.

> **Status (2026-11-15): ✅ RESOLVED.** `MAX_UPLOAD_SIZE_BYTES = 8 MB` +
> `ALLOWED_UPLOAD_TYPES` jpeg/png/webp enforced in `pickPhoto` with
> user-facing errors (`MealEditor.tsx:61-66,425-432`); sequence guard via
> `uploadSeqRef` with stale checks (`:130,446,452,464,469-472`); offline
> pre-check (`:440-445`); the shared 30 s `api()` AbortController timeout
> covers the request.

### 30. Frontend tooling: no strict TS, zero tests, minimal lint

- **Where (audit):** no `"strict": true`; no test script or test files;
  `@types/three` in dependencies; oxlint with 2 rules.

> **Status (2026-11-15): 🟡 PARTIALLY RESOLVED.**
> - Fixed: `strict: true` enabled in both `tsconfig.app.json:20` and
>   `tsconfig.node.json:17`; `@types/three` moved to `devDependencies`
>   (`package.json:26`).
> - **Remaining:** no `noUncheckedIndexedAccess`; still no test script and no
>   test files in `src`; `.oxlintrc.json` still has only 2 rules;
>   `three` (~600 KB) still ships for the landing animation with no
>   manualChunks strategy.

### 31. Untested high-risk paths across the codebase

- **Where (audit):** no backend tests for the ungrounded estimate path
  (`estimate_for_any_label`), `ensure_analyzed_catalog_foods`, `WeeklyView`,
  the client-supplied checkpoint parameter, or the duplicate-phone 500.

> **Status (2026-11-15): 🟡 PARTIALLY RESOLVED.**
> - Added backend tests: `test_duplicate_phone_returns_400_instead_of_500`,
>   `test_food_log_audit_and_daily_summary_and_weekly_view`,
>   `test_recognition_detail_rejects_untrusted_checkpoint_parameter`, plus the
>   nutrition-preview/goal-suggestions suite (`tests.py:323-390`)
>   (`backend/core/tests.py`). Suite now 74 tests OK (1 skipped).
> - **Remaining:** no tests for `estimate_for_any_label`'s ungrounded path or
>   `ensure_analyzed_catalog_foods`.

### 32. Live Gemini API key in a plaintext workspace `.env`

- **Where (audit):** `.env:7` contained a real-looking `GEMINI_API_KEY`
  (gitignored, never committed).

> **Status (2026-11-15): ✅ RESOLVED (in-repo).** `.env:8` is now
> `export GEMINI_API_KEY=` — no live key in the workspace; still gitignored
> and untracked. Note: whether the previously exposed token was rotated
> upstream is unknowable from the repo — if it was ever shared, rotate it
> regardless.

### 33. Monolithic frontend components and dead code

- **Where (audit):** MealEditor.tsx 1,112 lines; DoctorPortal.tsx 822;
  MealSenseScene.tsx 612; styles.css 3,711; AuthPage.tsx 368 lines of dead
  code; minors (no autosave debounce, 30 s polling, offset pagination risk,
  `name_bn` never displayed).

> **Status (2026-11-15): 🟡 PARTIALLY RESOLVED.**
> - Fixed: `AuthPage.tsx` deleted (auth consolidated in `LandingPage.tsx`);
>   draft autosave debounced 300 ms with cleanup (`MealEditor.tsx:239-241`);
>   DoctorPortal uses server-side `limit=100&offset=` pagination with a
>   "Load more" button (`api.ts:177-186`, `DoctorPortal.tsx:792-808,224-230`)
>   and its polling respects `document.visibilityState` (`:176`); `name_bn`
>   is now displayed — search matches Bengali names and results/entries show
>   them (`MealEditor.tsx:246-249,815,842`).
> - **Remaining:** MealEditor.tsx still 1,063 lines; DoctorPortal.tsx 798;
>   MealSenseScene.tsx 612; styles.css still 3,711 (Tailwind still unused);
>   App.tsx still polls doctor requests every 30 s on every page
>   (`App.tsx:204`).

### 34. Committed junk and information disclosure

- **Where (audit):** `tmp/pdfs/build_direction_note.py` with a foreign
  hardcoded path and a FastAPI description contradicting ADR-001; `tmp/` and
  `output/pdf/` (5 PNGs + generated PDF) committed; `backend/db.sqlite3`
  (553 KB, on disk, untracked) sitting next to tracked sources and could be
  accidentally added.

> **Status (2026-11-15): ✅ RESOLVED (staged).** `tmp/`, `output/`, and `.env`
> have no tracked files; the PDF deletion is staged;
> `git check-ignore` confirms `tmp/pdfs/build_direction_note.py` and
> `output/pdf/*` are ignored; the tmp/output files are also gone from disk.
> Same caveat as issue 7: deletions are staged, **not committed** — history
> still contains the blobs.

---

## Verified clean areas (for balance)

- No secrets or `.env` files committed to git (`.env.example` contains empty
  keys only; `db.sqlite3`, `private_media/`, `model_artifacts/` gitignored).
- Ownership checks are consistently enforced on meals, images, predictions,
  doctor requests, and custom foods; CSRF enforced and tested.
- `Decimal` is used correctly for all persisted nutrition math (`MealItem`,
  `nutrient_snapshot`, `totals()`); floats only appear inside the ML
  estimation layer (issue 3).
- MealItem nutrition snapshots keep history stable when catalog data changes
  (tested).
- `backend/model_artifacts.md` is a genuinely good provenance doc (SHA-256,
  source link, honest "0.6656 macro F1", explicit "does not establish
  redistribution rights").
- `local_recognition.py:31` uses `weights_only=True` and validates checkpoint
  metadata; `dinov3_recognition.py:74` honestly labels softmax output
  "uncalibrated".

---

## Remaining follow-ups (highest value first)

1. **Commit the staged deletions** (issues 7, 34) — they are only in the
   index; decide whether to rewrite history (git filter-repo) to purge the
   model binaries and junk from the repository history. Also commit the new
   `ml_models/data/fctb_2013_nutrition.db` (issue 6) so clones get the
   provenance-tracked source of truth.
2. **Move inference off the request path** (issue 10) — recognitions still
   block worker threads for tens of seconds on CPU.
3. **Fix the Meal PATCH version contract** (issue 18) — omitting `version`
   always 409s despite `required=False`.
4. **Resolve the `ml_models` packaging problem** (issue 14) — `backend/`
   alone is not deployable for recognition; the sys.path hack remains.
5. **Paginate patient meals/foods lists** (issue 15) and prune
   failed-recognition images (issue 27).
6. **Add frontend tests** + `noUncheckedIndexedAccess` (issue 30); backend
   tests for the ungrounded estimate path and catalog seeding (issue 31).
7. **Verify the FCTB 2013 rows against the publication** (issue 6) — check
   the 24 rows and codes against the INFS book and confirm its license/
   redistribution terms, then flip `verification_status` in the DB.
8. **Write `ModelVersion` records** (issue 23) — the model exists but is
   never populated.
9. **Evaluate the VLM on a held-out split** (issue 11) — portion MAE and
   ingredient F1 still do not exist; claims are honest but unevidenced.
10. **A11y stragglers** (issue 28): `Layout.tsx:212` alert,
    `SharingPage.tsx:77,84` confirm.
11. **Set a shared cache in production** (issue 9 caveat) — the default
    LocMemCache keeps throttle counters per-process.
