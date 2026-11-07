# MealSense implementation instructions

## Design authority

`MealSense ERD Report_V3.pdf` is the final **logical diagram and relationship source of truth** for this project. Use its four domain diagrams and the cross-diagram integrity rules when changing the data model. `AGENTS.md` describes the intended engineering approach. `MealSense PRD.docx.pdf` remains the draft source for product behavior and release priority. Where V3 adds a feature beyond that PRD, record the scope decision and implement it as a separate feature; do not silently present proposed clinical or doctor workflows as part of the food-logging MVP.

The PDF contains Mermaid source listings rather than rendered diagrams. Read the relationship descriptions and constraints alongside those listings. Existing Django code is the source of truth for what is already implemented; migrate it incrementally rather than replacing data or public API contracts in one step.

## Rules to implement from V3

1. A saved meal has at least one item. A draft may be empty. A meal may reference one user-owned private image. A private upload and a catalogue image have different ownership and retention rules.
2. `MealItem.quantity_in_grams` is the confirmed amount used for nutrition calculations. Recognition labels and photo portion estimates are suggestions. A user action saves the meal. Manual entry must work when recognition or catalogue matching fails.
3. Preserve food name, nutrient amounts, source, basis, and calculation version with a logged item. Catalogue corrections never rewrite old meals automatically. Explicit user edits recalculate and replace affected snapshots and increment the meal version.
4. A client operation ID is unique per user. A retry with the same payload returns the original result; reuse with a different payload is a conflict. The operation points to the resulting meal, never the reverse. Keep creation and operation completion atomic.
5. A recognition result may have no catalogue food. Preserve the original label. It may reference a detected region from the same session. A session without completed inference may have no model version.
6. `NutritionRecord` is the only versioned nutrient value source; `FoodNutrition` selects one approved record of the same food. Serving conversions are food-specific, with a defined preparation and edible gram basis. Unknown nutrient values remain unknown.
7. Numeric goals live in `NutrientTarget`; progress refers to a specific target and goal version. Daily summaries are optional, rebuildable caches with one row per user and local date. The user's validated timezone controls date grouping.
8. Check owner consistency across meal, image, recognition, goal, and doctor sharing links. Use backend authorization for every private read or mutation. Shared meals must belong to the consenting patient.
9. A private-image deletion request must detach or remove permitted references under a defined retention policy, then delete storage bytes. Track failures and retry; retained references must not keep unwanted bytes forever.

## Scope and unresolved decisions

- Manual food entry may create a private reusable `Food` or store a source-labelled item snapshot; it must not require an approved public catalogue item.
- Doctor collaboration, disease rules, and dietary recommendations in V3 are later product capabilities. They require a clinical owner, consent and access policy, review process, and intended-use decision before a user-facing launch. No diagnosis or automated prescription follows from the diagram alone.
- Production image retention, nutrition dataset licence, AI runtime, and offline mutation policy remain decisions. Keep local development behavior explicit until chosen.
- Keep current `/api/v1/` contracts stable where possible, and update serializers, frontend types, and tests together when a contract changes.

## Current implementation map

The backend still uses one Django app, `core`, with session authentication and CSRF. Its existing `FoodImage` model represents a **private user upload** despite its legacy name, with `PrivateMealImage` as a proxy. `FoodPrediction` represents a recognition session, with `RecognitionSession` as a proxy; structured `RecognitionResult` rows supplement its existing JSON response. `MealItem` is the consumption ledger. `NutritionRecord` holds versioned food values and `FoodNutrition` selects an approved public record. `FoodServing` defines a food-specific edible gram conversion. `NutritionGoal` and `NutrientTarget` version goals; daily progress is computed from saved meal items. `MediaDeletionJob` retries private storage deletion. Existing API routes and legacy food fields remain during migration.

V3 is the final **logical design**, not a claim that every class is already shipped. The current app does not yet include recipe composition, ingredient nutrient calculation, detected image regions, portion estimation, dataset management, catalogue image moderation, daily summary caching, recommendation delivery, or doctor collaboration. Add these as reviewed vertical features with migrations, API authorization, UI, and tests. Until then, do not model their absence as a zero nutrient value or fabricate estimates. Complete the food and nutrition workflow before using V3's clinical extensions.
