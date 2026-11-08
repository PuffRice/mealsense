# MealSense --- Agent Instructions

> **Purpose:** This file is the working agreement for AI coding agents
> and human contributors working in the MealSense codebase. Read it
> before making changes.
>
> **Project status:** This document captures the intended architecture
> and domain model. It is not proof that every listed module or class
> already exists in the repository. Inspect the actual codebase before
> editing, preserve established conventions where they are sound, and
> update this document when the implementation materially changes.

------------------------------------------------------------------------

## 1. Product Overview

MealSense is a food recognition and nutrition-tracking application
focused on reliable food identification, nutrition calculation, meal
logging, and progress monitoring. It is intended to support
international foods and Bangladesh-specific foods, names, recipes,
portions, and preparation variations.

### Core user journey

1.  A user creates an account and configures profile, preferences, and
    nutrition goals.
2.  The user uploads or captures a food image.
3.  The recognition pipeline detects one or more food regions and
    generates candidate food classifications.
4.  The system maps model labels to canonical `Food` records.
5.  A portion-estimation component estimates quantity where supported.
6.  The user reviews and confirms or corrects the prediction and
    portion.
7.  The system retrieves an applicable, source-backed nutrition record
    and calculates nutrients for the consumed quantity.
8.  The user saves the food as a `MealItem` within a `Meal`.
9.  Daily summaries and goal progress are recalculated from persisted
    meal items.
10. Recommendation and notification services may use the user's
    consented preferences and nutrition history.

### Product principles

-   **Nutrition data must be traceable.** Every published nutrition
    value must have a known basis, source or calculation method, and
    verification state.
-   **AI identifies; the nutrition domain calculates.** Do not let a
    vision model invent calorie, protein, carbohydrate, or fat values.
-   **User confirmation matters.** Predictions and estimates are
    proposals until accepted or corrected where the workflow requires
    confirmation.
-   **Historical logs must be stable.** Updating a food's nutrition data
    must not silently rewrite what a user logged in the past.
-   **Unknown is not zero.** A missing nutrient value must remain
    unknown (`NULL`/absent), not be converted to zero.
-   **Bangladesh food context is first-class.** Support Bengali names,
    aliases, local serving conventions, and preparation variants without
    assuming every recipe has one universal nutrition profile.
-   **Keep domain logic testable.** Put cross-entity business workflows
    in services rather than large model methods or API views.

------------------------------------------------------------------------

## 2. Expected Technology Direction

The intended stack is:

  -----------------------------------------------------------------------
  Area                                Technology
  ----------------------------------- -----------------------------------
  Backend                             Python, Django

  API                                 Django REST Framework

  Database                            PostgreSQL

  Frontend                            React, TypeScript

  Styling                             Tailwind CSS

  AI/ML                               Python; model framework selected by
                                      the recognition implementation

  Image storage                       Django storage abstraction;
                                      production object storage may be
                                      configured

  API format                          JSON over REST

  Deployment                          Environment-driven configuration
  -----------------------------------------------------------------------

Do not assume a particular package, version, deployment provider, task
queue, or ML architecture unless it is present in the repository or
explicitly approved. Inspect `pyproject.toml`, `requirements*.txt`,
`package.json`, lockfiles, Docker files, environment examples, and CI
configuration first.

### Repository discovery before coding

At the start of a task:

1.  Inspect the root directory and existing README/architecture
    documents.
2.  Identify backend and frontend entry points.
3.  Inspect Django settings, installed apps, URL configuration, model
    modules, serializers, views, services, and tests.
4.  Inspect frontend routes, API client, state management, component
    conventions, and types.
5.  Check migrations and the current database schema before changing
    models.
6.  Search for existing implementations before creating new classes.
7.  Run the existing tests or relevant checks to establish a baseline.

Never replace an existing architecture simply because this document
shows an intended structure. Reconcile the current code with the target
design incrementally.

------------------------------------------------------------------------

## 3. Domain Architecture: Eight Modules

The logical domain is divided into eight modules. Django app boundaries
may differ if the existing repository has a good reason, but
responsibilities should remain separated.

  -----------------------------------------------------------------------
  \#                      Module                  Primary
                                                  responsibilities
  ----------------------- ----------------------- -----------------------
  01                      User Management         Accounts, profile,
                                                  preferences, broad
                                                  dietary goals

  02                      Food Database           Canonical foods,
                                                  categories, nutrition,
                                                  servings, images,
                                                  aliases, variants

  03                      Ingredient & Recipe     Ingredients, recipes,
                                                  recipe composition,
                                                  cooking methods

  04                      AI Recognition          Recognition sessions,
                                                  candidate results,
                                                  detections, portion
                                                  estimates, model
                                                  versions

  05                      Meal & Nutrition        Meals, meal items,
                          Tracking                food-log audit events,
                                                  daily summaries

  06                      Nutrition & Health      Quantified goals,
                          Goals                   nutrient targets,
                                                  progress

  07                      Data Management         Nutrition sources,
                                                  versioned nutrition
                                                  records, datasets,
                                                  dataset images,
                                                  contributions

  08                      Recommendation System   Food recommendations,
                                                  feedback, notifications
  -----------------------------------------------------------------------

### Module ownership

-   `accounts` owns authentication identity and user-specific settings.
-   `foods` owns canonical food identity and classification.
-   `nutrition` owns nutrient records, source provenance, calculations,
    and validation.
-   `recipes` owns recipe and ingredient composition.
-   `recognition` owns inference sessions, predictions, detections,
    portion estimates, and model metadata.
-   `meals` owns actual consumption records and daily aggregation.
-   `goals` owns targets and progress.
-   `datasets` owns dataset ingestion, image metadata, and contribution
    review.
-   `recommendations` owns recommendation records and feedback.
-   `notifications` owns delivery-ready notification records, if kept
    separate from recommendations.

Avoid circular imports between Django apps. Use string model references,
`settings.AUTH_USER_MODEL`, service boundaries, and carefully chosen app
dependencies.

------------------------------------------------------------------------

## 4. UML Domain Model

The following is the intended logical class model. It is deliberately
more detailed than a physical schema. A class may map to a Django model,
a value object, or a service depending on its responsibility. Do not
create database tables for service classes.

### 4.1 User Management

#### `User`

Authentication identity. Prefer a custom Django user model configured at
project start.

Expected responsibilities: - Account registration and authentication
integration. - Account activation/deactivation. - Permissions and staff
status. - Password management through Django's authentication
mechanisms.

Do not store plain-text passwords. Do not implement custom password
hashing.

#### `UserProfile`

One-to-one extension for profile information: - `user` - `full_name` -
`date_of_birth` (optional) - `gender` (optional and only if product
requirements justify it) - `height_cm` - `current_weight_kg` -
`activity_level` - `profile_image`

Possible calculations: BMI, estimated BMR, and estimated TDEE. These are
estimates, not medical measurements. Do not infer health diagnoses.

#### `UserPreference`

One-to-one user settings: - language (`en`, `bn`, future locale codes) -
measurement system - preferred serving unit - notification preferences -
food preferences - accessibility/UI preferences if needed

#### `DietaryGoal`

A broad user intention, such as weight management or balanced eating.
Keep this concept distinct from quantified `NutritionGoal` targets.
Avoid duplicating the same goal in two places without a clear lifecycle
distinction.

### 4.2 Food Database

#### `Food`

Canonical food identity. It should not contain a user's consumption
history or an image-specific prediction confidence.

Expected fields: - `id` - `category` - `name` - `name_bn` - `slug` -
`description` - `is_active` - `is_verified` - `ml_class_id` or an
explicit mapping relation if one food can have multiple model labels -
timestamps

Expected behavior: - display-name selection by locale - retrieve
applicable nutrition profile - retrieve available serving options -
retrieve primary image - retrieve aliases and variants

#### `FoodCategory`

Hierarchical food categorization using an optional self-reference
`parent`. Examples include rice/staples, fish, meat, vegetables, fruits,
snacks, and beverages. Prevent category cycles.

#### `FoodNutrition`

The currently selected or published nutrition profile for a food,
expressed on a clearly defined basis, normally per 100 g edible portion.
Keep nutrient fields nullable where data is unavailable. Include
source/provenance and verification state, or link to a versioned
`NutritionRecord`.

Suggested nutrients: - energy (kcal) - protein (g) - carbohydrate (g) -
total fat (g) - saturated fat (g) - trans fat (g) - dietary fiber (g) -
total sugars (g) - sodium (mg) - cholesterol (mg) - selected minerals
and vitamins

Use consistent units and document whether carbohydrate includes fiber
according to the source's convention. Do not combine values from
incompatible sources without a documented normalization policy.

#### `FoodServing`

Serving conversion for a particular food: - serving label and localized
label - quantity/unit - equivalent edible weight in grams - default flag

A serving called "one plate" is food-specific and approximate. Never
assume one plate has the same weight for all foods.

#### `FoodImage`

Reference images for a canonical food: - image storage key - image type
(catalog/reference/user-submitted if applicable) - source URL/platform -
license/permission evidence - content hash - primary flag -
moderation/verification state

A dataset training image and a user-uploaded recognition image are not
automatically the same asset or subject to the same retention rules.

#### `FoodAlias`

Localized or regional aliases for food search and model-label mapping.
Normalize aliases for matching, but preserve the original display form
and language/region metadata.

#### `FoodVariant`

Represents a preparation or product variation linked to a base food.
Examples: plain khichuri, bhuna khichuri, chicken khichuri; plain rice
versus fried rice. Use a clear relationship between base food and
variant. Avoid duplicate records and self-referencing variants.

#### `Allergen` and `FoodAllergen`

Optional but recommended safety domain: - allergen identity and code -
food-to-allergen relationship - presence type (contains, may contain,
derived from, unknown) - evidence/source and verification status

Do not infer allergen safety merely because no allergen row exists.

### 4.3 Ingredient & Recipe

#### `Ingredient`

A raw or prepared ingredient with canonical/localized names and optional
linkage to a food-composition record. Avoid maintaining a second
conflicting nutrition database for ingredients.

#### `Recipe`

A specific preparation of a food: - food reference (where applicable) -
title/description/instructions - cooking method - preparation/cooking
time - number of servings - raw and final cooked weights - recipe
version and status

A food can exist without a recipe. One food may have multiple recipes or
regional preparations.

#### `RecipeIngredient`

Join entity between recipe and ingredient. Stores quantity, unit,
normalized weight, edible weight, and preparation note. This is a real
domain entity, not merely an implicit many-to-many field.

#### `CookingMethod`

Controlled vocabulary such as boiling, steaming, shallow frying, deep
frying, grilling, roasting, and baking. Cooking method alone does not
determine exact nutrient retention or oil absorption.

Recipe nutrition should be calculated from ingredient quantities and
source-backed ingredient nutrition, with documented assumptions for
edible yield, cooking yield, oil absorption, and nutrient retention. The
final cooked weight is important when deriving nutrition per 100 g of
prepared dish.

### 4.4 AI Recognition

#### `RecognitionSession`

One recognition operation: - initiating user (nullable only if anonymous
recognition is explicitly supported) - uploaded image reference -
selected model version - status - timestamps - failure/error metadata

Use explicit states such as `PENDING`, `PROCESSING`, `COMPLETED`,
`FAILED`, and `CANCELLED`. Validate allowed transitions.

#### `RecognitionResult`

One candidate prediction: - session - canonical food - rank - confidence
score - user-confirmation state - selected state - timestamps

One session can return multiple candidate foods. Confidence belongs to
this prediction, not to `Food`.

#### `FoodDetection`

One detected region in an image: - session - optional matched food -
bounding box and/or segmentation reference - detection confidence -
stable detection index

Use a documented coordinate convention (normalized 0--1 or pixel
coordinates with image dimensions). Validate box boundaries and
dimensions.

#### `PortionEstimate`

One estimate associated with a detection/result: - estimated grams
and/or volume - serving interpretation - estimation method -
confidence/uncertainty - model version or estimator metadata

Classification confidence and portion-estimation confidence are
different quantities. A visually correct food label does not imply an
accurate weight estimate.

#### `ModelVersion`

Tracks the model artifact and evaluation metadata: - model
name/version/architecture - artifact reference - lifecycle status -
deployed timestamp - evaluation metrics and dataset reference where
appropriate

Do not store secrets or large model binaries directly in ordinary
database columns.

### 4.5 Meal & Nutrition Tracking

#### `Meal`

A user's meal occasion: - user - meal type - date/time and timezone
policy - notes - timestamps

#### `MealItem`

An individual consumed food within a meal: - meal - canonical food -
optional serving - quantity and normalized grams - optional origin
recognition result - nutrient snapshots at logging time -
creation/update timestamps

The `MealItem` is the primary record of actual food consumption. Store
the calculated energy/macronutrient values (and other tracked nutrients)
as snapshots or use an immutable nutrition-record reference plus
quantity and calculation version. Historical values must remain
explainable when catalog data changes.

#### `FoodLog`

Use as an audit/event history, not a second consumption ledger. It can
record add/edit/remove/correction events for a `MealItem`, including
actor, action, previous/new values, and timestamp. Decide whether audit
events survive deletion; if so, use a nullable relation plus stable item
identifier/snapshot.

#### `DailyNutritionSummary`

Derived aggregation for a user and local calendar date: - total
nutrients - meal count - computation timestamp/version

Enforce one summary per user/date. It is a cache/read model, not the
source of truth. Rebuild it from meal items when necessary. Define
timezone behavior so entries near midnight are assigned consistently.

### 4.6 Nutrition & Health Goals

#### `NutritionGoal`

A time-bounded user goal. Keep broad intention (`DietaryGoal`) and
numeric target lifecycle aligned; if they are effectively duplicates in
the implementation, consolidate rather than maintain two competing
sources of truth.

#### `NutrientTarget`

A target for one nutrient and unit, with a target type (minimum,
maximum, range, or exact target). Validate unit and nutrient
compatibility.

#### `GoalProgress`

A dated measurement of actual versus target. It should be reproducible
from the meal history and target version. Do not interpret progress as a
medical assessment.

### 4.7 Data Management

#### `NutritionSource`

Source registry: - name/type - URL or publication reference -
license/terms - retrieval date - trust/verification metadata

#### `NutritionRecord`

Versioned source-backed nutrient payload: - food - source - source
reference - version - basis quantity/unit (normally 100 g edible
portion) - nutrient values - verification status - effective date and
creation timestamp - calculation/normalization notes

Retain historical revisions. Do not overwrite source data without an
auditable revision. The active `FoodNutrition` profile should identify
which record/version was selected.

#### `Dataset`

Dataset identity/version, purpose, source, status, split policy, and
summary statistics.

#### `DatasetImage`

A dataset membership/annotation record linked to a stored image asset
and canonical food label: - dataset - food - image reference or storage
key - source and license/permission evidence - content hash -
train/validation/test split - annotation/moderation status

Prevent duplicate or near-duplicate images from crossing dataset splits.
Keep provenance and permission evidence. Do not scrape or ingest
private/restricted content or bypass platform access controls.

#### `DataContribution`

User-submitted food image/data with moderation lifecycle: -
contributor - optional proposed food - submission content - status -
reviewer - review timestamps - rejection reason

A contribution must not become trusted catalog or training data until
reviewed and rights/consent requirements are satisfied.

### 4.8 Recommendation System

#### `FoodRecommendation`

A generated suggestion: - user - recommended food - recommendation
type - reason/explanation - score - lifecycle status - creation/expiry
timestamps - algorithm/model version where relevant

Recommendations should respect known allergies, dietary restrictions,
user preferences, and product safety rules. Do not present a
recommendation as medical advice.

#### `RecommendationFeedback`

User response to a recommendation: - recommendation - user - feedback
type/rating/comment - timestamp

Validate that feedback belongs to the intended user and recommendation.

#### `Notification`

User-facing notification record: - user - title/message/type - read
state and timestamps - delivery state/channel metadata if delivery is
implemented

Avoid duplicate notifications and respect notification preferences.

------------------------------------------------------------------------

## 5. UML Relationship Baseline

Use the following relationship intent when implementing the models.

  -----------------------------------------------------------------------------------------
  Parent / owner       Related class                     Multiplicity Meaning
  -------------------- ------------------------ --------------------- ---------------------
  User                 UserProfile                          1 to 0..1 Optional one-to-one
                                                                      profile

  User                 UserPreference                       1 to 0..1 Optional one-to-one
                                                                      preferences

  User                 DietaryGoal                         1 to 0..\* User may define
                                                                      multiple goals

  FoodCategory         FoodCategory                     0..1 to 0..\* Parent category
                                                                      hierarchy

  FoodCategory         Food                                1 to 0..\* Category contains
                                                                      foods

  Food                 FoodNutrition                       1 to 0..\* Nutrition
                                                                      profiles/revisions

  Food                 FoodServing                         1 to 0..\* Food-specific serving
                                                                      options

  Food                 FoodImage                           1 to 0..\* Reference images

  Food                 FoodAlias                           1 to 0..\* Localized aliases

  Food                 FoodVariant                         1 to 0..\* Base-to-variant
                                                                      relationship

  Food                 FoodAllergen                        1 to 0..\* Allergen declarations

  Allergen             FoodAllergen                        1 to 0..\* Allergen referenced
                                                                      by declarations

  Food                 Recipe                              1 to 0..\* Food may have
                                                                      multiple preparations

  Recipe               RecipeIngredient                    1 to 1..\* Recipe has ingredient
                                                                      lines

  Ingredient           RecipeIngredient                    1 to 0..\* Ingredient used by
                                                                      recipes

  CookingMethod        Recipe                              1 to 0..\* Method used by
                                                                      recipes

  User                 RecognitionSession                  1 to 0..\* User initiates
                                                                      sessions

  ModelVersion         RecognitionSession                  1 to 0..\* Session uses a model
                                                                      version

  RecognitionSession   RecognitionResult                   1 to 0..\* Session returns
                                                                      candidate results

  RecognitionSession   FoodDetection                       1 to 0..\* Session detects
                                                                      regions

  Food                 RecognitionResult                   1 to 0..\* Food may be a
                                                                      predicted candidate

  RecognitionResult    PortionEstimate                     1 to 0..\* Result may have
                                                                      estimates/revisions

  User                 Meal                                1 to 0..\* User owns meals

  Meal                 MealItem                            1 to 0..\* Meal contains
                                                                      consumed items

  Food                 MealItem                            1 to 0..\* Food appears in meal
                                                                      items

  FoodServing          MealItem                         0..1 to 0..\* Optional serving
                                                                      reference

  RecognitionResult    MealItem                         0..1 to 0..\* Optional recognition
                                                                      origin

  MealItem             FoodLog                             1 to 0..\* Audit events for an
                                                                      item

  User                 DailyNutritionSummary               1 to 0..\* User has daily
                                                                      summaries

  User                 NutritionGoal                       1 to 0..\* User sets nutrition
                                                                      goals

  NutritionGoal        NutrientTarget                      1 to 1..\* Goal defines targets

  NutritionGoal        GoalProgress                        1 to 0..\* Goal has progress
                                                                      observations

  NutritionSource      NutritionRecord                     1 to 0..\* Source provides
                                                                      records

  Food                 NutritionRecord                     1 to 0..\* Food has sourced
                                                                      revisions

  Dataset              DatasetImage                        1 to 0..\* Dataset contains
                                                                      image memberships

  Food                 DatasetImage                        1 to 0..\* Image membership has
                                                                      a food label

  FoodImage            DatasetImage                     0..1 to 0..\* Dataset membership
                                                                      may reference an
                                                                      image asset

  User                 DataContribution                    1 to 0..\* User submits
                                                                      contributions

  User                 DataContribution                 0..1 to 0..\* Optional reviewer
                       reviewer                                       

  User                 FoodRecommendation                  1 to 0..\* User receives
                                                                      recommendations

  Food                 FoodRecommendation                  1 to 0..\* Food is recommended

  FoodRecommendation   RecommendationFeedback              1 to 0..\* Recommendation
                                                                      receives feedback

  User                 RecommendationFeedback              1 to 0..\* User submits feedback

  User                 Notification                        1 to 0..\* User receives
                                                                      notifications
  -----------------------------------------------------------------------------------------

### Relationship semantics

-   Use **composition** only when the child lifecycle is owned by the
    parent and deletion is intended to cascade.
-   Use **association** for independent records linked by a foreign key.
-   Use **aggregation** sparingly; do not use it just to decorate a
    diagram.
-   A Django `ForeignKey` does not automatically mean UML composition.
-   Define `on_delete` behavior deliberately for every relation. Prefer
    `PROTECT`/`RESTRICT` for catalog data whose deletion would damage
    history, and `CASCADE` only for genuinely owned dependent records.
-   Use explicit through models for relationships that have their own
    attributes or lifecycle.

------------------------------------------------------------------------

## 6. Mermaid UML Diagram

This is the compact canonical class diagram for the domain. Keep it
synchronized with actual model names and relationships. For a very large
diagram, split it into module diagrams while retaining the same
relationship definitions.

``` mermaid
classDiagram
direction LR

class User
class UserProfile
class UserPreference
class DietaryGoal

class Food
class FoodCategory
class FoodNutrition
class FoodServing
class FoodImage
class FoodAlias
class FoodVariant
class Allergen
class FoodAllergen

class Ingredient
class Recipe
class RecipeIngredient
class CookingMethod

class RecognitionSession
class RecognitionResult
class FoodDetection
class PortionEstimate
class ModelVersion

class Meal
class MealItem
class FoodLog
class DailyNutritionSummary

class NutritionGoal
class NutrientTarget
class GoalProgress

class NutritionSource
class NutritionRecord
class Dataset
class DatasetImage
class DataContribution

class FoodRecommendation
class RecommendationFeedback
class Notification

User "1" *-- "0..1" UserProfile
User "1" *-- "0..1" UserPreference
User "1" --> "0..*" DietaryGoal

FoodCategory "0..1" --> "0..*" FoodCategory : parent
FoodCategory "1" --> "0..*" Food
Food "1" *-- "0..*" FoodNutrition
Food "1" *-- "0..*" FoodServing
Food "1" *-- "0..*" FoodImage
Food "1" *-- "0..*" FoodAlias
Food "1" --> "0..*" FoodVariant
Food "1" --> "0..*" FoodAllergen
Allergen "1" --> "0..*" FoodAllergen

Food "1" --> "0..*" Recipe
CookingMethod "1" --> "0..*" Recipe
Recipe "1" *-- "1..*" RecipeIngredient
Ingredient "1" --> "0..*" RecipeIngredient

User "1" --> "0..*" RecognitionSession
ModelVersion "1" --> "0..*" RecognitionSession
RecognitionSession "1" *-- "0..*" RecognitionResult
RecognitionSession "1" *-- "0..*" FoodDetection
Food "1" --> "0..*" RecognitionResult
Food "1" --> "0..*" FoodDetection
RecognitionResult "1" *-- "0..*" PortionEstimate

User "1" --> "0..*" Meal
Meal "1" *-- "0..*" MealItem
Food "1" --> "0..*" MealItem
FoodServing "0..1" --> "0..*" MealItem
RecognitionResult "0..1" --> "0..*" MealItem
MealItem "1" --> "0..*" FoodLog
User "1" --> "0..*" FoodLog
User "1" --> "0..*" DailyNutritionSummary

User "1" --> "0..*" NutritionGoal
NutritionGoal "1" *-- "1..*" NutrientTarget
NutritionGoal "1" *-- "0..*" GoalProgress

Food "1" --> "0..*" NutritionRecord
NutritionSource "1" --> "0..*" NutritionRecord
Dataset "1" *-- "0..*" DatasetImage
Food "1" --> "0..*" DatasetImage
FoodImage "0..1" --> "0..*" DatasetImage
User "1" --> "0..*" DataContribution

User "1" --> "0..*" FoodRecommendation
Food "1" --> "0..*" FoodRecommendation
FoodRecommendation "1" *-- "0..*" RecommendationFeedback
User "1" --> "0..*" RecommendationFeedback
User "1" --> "0..*" Notification
```

------------------------------------------------------------------------

## 7. Backend Application Structure

Current recognition implementation lives in the consolidated `backend/core/`
app. `services.recognize_with_provider` routes `AI_PROVIDER=local` to
`local_recognition.py`, which loads the BanglaFoodNet architecture in
`banglafoodnet.py`. Checkpoints and reference notebooks are downloaded into
the ignored `backend/model_artifacts/banglafoodnet/` folder; provenance is in
`backend/model_artifacts.md`. Local inference uses only the supervised dish
head, checkpoint label order, and training evaluation transforms. It does
not provide portions, nutrition, ingredient safety, or non-food rejection.
The existing cloud adapters remain selectable explicitly; local failures
keep manual logging available without sending photos to a cloud provider.

Use the following as a target structure, not a mandate to reorganize a
working repository without reason.

``` text
backend/
├── config/
│   ├── settings/
│   ├── urls.py
│   ├── asgi.py
│   └── wsgi.py
├── apps/
│   ├── accounts/
│   │   ├── models/
│   │   ├── serializers/
│   │   ├── views/
│   │   ├── services/
│   │   ├── permissions.py
│   │   └── tests/
│   ├── foods/
│   │   ├── models/
│   │   ├── serializers/
│   │   ├── views/
│   │   ├── selectors/
│   │   ├── services/
│   │   └── tests/
│   ├── nutrition/
│   │   ├── models/
│   │   ├── calculators/
│   │   ├── validators/
│   │   ├── services/
│   │   └── tests/
│   ├── recipes/
│   ├── recognition/
│   │   ├── models/
│   │   ├── classifiers/
│   │   ├── estimators/
│   │   ├── inference/
│   │   ├── services/
│   │   └── tests/
│   ├── meals/
│   │   ├── models/
│   │   ├── serializers/
│   │   ├── views/
│   │   ├── services/
│   │   ├── analytics/
│   │   └── tests/
│   ├── goals/
│   ├── datasets/
│   │   ├── models/
│   │   ├── ingestion/
│   │   ├── validation/
│   │   └── tests/
│   ├── recommendations/
│   └── notifications/
├── shared/
│   ├── enums/
│   ├── exceptions/
│   ├── permissions/
│   └── utilities/
├── manage.py
└── requirements.txt
```

Each app may use a simpler layout if it has few files. Do not create
empty abstraction directories just to match this tree.

### Layer responsibilities

  Layer                Responsibility
  -------------------- ------------------------------------------------------
  Models               Persistence, constraints, simple local invariants
  Managers/querysets   Reusable database query behavior
  Selectors            Read/query logic when complexity warrants it
  Services             Cross-model business workflows and transactions
  Calculators          Deterministic nutrition and aggregation calculations
  Validators           Domain-specific validation
  Serializers          API input validation and output representation
  Views/viewsets       HTTP orchestration, authentication, permissions
  Tasks                Asynchronous jobs if a task queue exists
  Tests                Unit, integration, API, and ML pipeline tests

Avoid putting complex calculations, external API calls, model inference,
or multi-model workflows in Django model `save()` methods or
serializers.

------------------------------------------------------------------------

## 8. Backend Engineering Rules

### Django models and migrations

-   Use `settings.AUTH_USER_MODEL` for relations to the user model.
-   Configure the custom user model before the first migration if the
    project is still at that stage.
-   Use `DecimalField` for persisted nutrition quantities and money-like
    precision; do not use binary floating point for authoritative
    nutrition totals.
-   Define `related_name` explicitly for important relationships.
-   Add database constraints for invariants that must hold under
    concurrent requests.
-   Add indexes based on real query patterns, not on every field.
-   Use `UniqueConstraint` for natural uniqueness such as one daily
    summary per user/date.
-   Use `CheckConstraint` for valid positive quantities and valid ranges
    where appropriate.
-   Use `PROTECT` for catalog/source records referenced by historical
    data where deletion would destroy provenance.
-   Use migrations for every schema change. Never edit an applied
    migration to change production history.
-   Avoid `null=True` on strings unless there is a clear distinction
    between null and blank; use one consistent convention.
-   Use explicit status choices/enums and validate state transitions.

### API and serializers

-   Validate all user-controlled input on the server.
-   Enforce object-level ownership: a user must not read or modify
    another user's meals, profile, recognition sessions, goals, or
    contributions.
-   Use pagination for food search, image collections, logs, and
    recommendation lists.
-   Filter and sort using allowlisted fields.
-   Use `select_related()` and `prefetch_related()` for serializer
    relationship traversal where needed. DRF does not automatically
    optimize these querysets.
-   Keep serializers focused on validation and representation; delegate
    business workflows to services.
-   Return consistent error structures and appropriate HTTP status
    codes.
-   Version public APIs if breaking changes become necessary.
-   Do not expose internal storage paths, private source credentials, or
    model artifact locations.

### Transactions and consistency

Use database transactions for workflows that must succeed or fail
together, especially: - creating a meal item and its nutrition
snapshot; - accepting a recognition result into a meal; - approving a
contribution and publishing its catalog record; - updating a goal and
its target set; - recording an audit event alongside a change.

Do not hold database transactions open while running slow model
inference or external network calls. Persist job/session state, perform
the work outside the transaction, then save the result in a short
transaction.

------------------------------------------------------------------------

## 9. Nutrition Calculation Rules

### Baseline formula

For a food with nutrient value per 100 g:

`portion_nutrient = nutrient_per_100g * consumed_weight_g / 100`

For example, if a food has 180 kcal per 100 g and the consumed amount is
250 g:

`180 * 250 / 100 = 450 kcal`

### Required rules

1.  Store the nutrient basis explicitly (for example, per 100 g edible
    portion).
2.  Convert serving quantities to grams using the selected food-specific
    serving record.
3.  Do not apply a per-100-g formula to a volume measure until a valid
    density or serving conversion is available.
4.  Preserve unknown nutrient values as unknown.
5.  Use `Decimal` for persisted and authoritative calculations.
6.  Define rounding rules centrally and apply them consistently at
    API/display boundaries.
7.  Keep raw-source values and normalized values distinguishable.
8.  Record calculation version or nutrition-record reference in
    historical logs when needed for reproducibility.
9.  Do not assume calorie energy is always exactly `4P + 4C + 9F`;
    source methods, fiber, rounding, and food-specific factors can
    differ.
10. Recipe calculations must account for final cooked weight when
    calculating nutrients per 100 g of the prepared dish.

### Recipe nutrition

At a high level:

1.  Resolve each recipe ingredient to a source-backed nutrient profile.
2.  Convert ingredient amounts into compatible edible weights.
3.  Calculate each ingredient's nutrient contribution.
4.  Apply documented yield, retention, and absorption factors where data
    exists.
5.  Sum nutrient contributions.
6.  Divide by final cooked weight for per-100-g values.
7.  Divide by servings only if serving count and distribution
    assumptions are valid.
8.  Store the calculation method, input record versions, and
    assumptions.

Do not fabricate exact oil absorption, cooking retention, or final dish
composition.

------------------------------------------------------------------------

## 10. AI Recognition and Portion Estimation Rules

### Recognition pipeline

Recommended conceptual pipeline:

`ImageUpload -> ImageValidation -> FoodDetection -> FoodClassification -> FoodMatching -> PortionEstimation -> UserReview -> MealItem`

-   `ImageValidation`: format, size, dimensions, corruption, and safety
    checks.
-   `FoodDetection`: zero or more regions/food objects.
-   `FoodClassification`: ranked candidate labels and scores.
-   `FoodMatching`: maps model labels to canonical Food IDs and aliases.
-   `PortionEstimation`: estimates grams/volume using a documented model
    or method.
-   `UserReview`: allows correction and confirmation.
-   `MealItem`: created only after the user accepts or the product
    explicitly supports a safe auto-log workflow.

### AI rules

-   Keep model inference behind a service/interface so models can be
    replaced.
-   Persist model version and relevant preprocessing configuration.
-   Validate confidence ranges.
-   Do not treat confidence as calibrated probability unless the model
    has been calibrated and evaluated.
-   Keep classification and portion-estimation metrics separate.
-   Support an unknown/unsupported-food outcome.
-   Do not force a low-confidence prediction into the closest catalog
    food.
-   Do not claim exact grams from a single RGB image unless the method
    has evidence supporting that precision.
-   Handle multiple dishes and overlapping detections.
-   Avoid logging raw uploaded images or sensitive metadata in
    application logs.
-   Apply upload limits, image validation, authorization, and retention
    policies.

------------------------------------------------------------------------

## 11. Food Dataset and Nutrition Data Governance

### Nutrition data ingestion

For every imported nutrition record, preserve: - source name and source
URL/publication reference; - retrieval timestamp; - license/usage
terms; - original food identifier; - original nutrient values and
units; - normalized values and basis; - mapping decision to canonical
Food; - reviewer/verification state; - import batch/version.

Potential public references to evaluate include USDA FoodData Central,
Open Food Facts, and published Bangladesh food composition tables.
Verify each source's coverage, methodology, license, and applicability
before importing. Do not assume a global database accurately represents
a Bangladeshi home-cooked recipe.

### Image data ingestion

-   Store source URL/platform and license/permission evidence.
-   Respect source platform terms and access controls.
-   Do not bypass authentication, private-group restrictions, CAPTCHAs,
    or technical access controls.
-   Track image hashes and near-duplicate relationships.
-   Review labels and image quality.
-   Prevent leakage across train/validation/test splits.
-   Keep user-contributed images separate until consent and review
    requirements are satisfied.
-   Support takedown/removal workflows where required.

------------------------------------------------------------------------

## 12. Security, Privacy, and Safety

-   Use Django's password and session/token security mechanisms.
-   Keep secrets in environment variables or a secret manager. Never
    commit `.env`, API keys, tokens, or credentials.
-   Use HTTPS in deployed environments.
-   Apply authentication and object-level authorization to all personal
    records.
-   Validate image uploads and restrict file size/type.
-   Store uploaded files outside executable/static code paths.
-   Avoid exposing user images publicly by default.
-   Minimize personal data collection.
-   Define retention/deletion behavior for uploaded images, account
    data, and logs.
-   Use rate limiting for authentication, uploads, recognition, and
    expensive endpoints.
-   Do not log passwords, tokens, sensitive request bodies, or private
    image URLs.
-   Treat nutrition information as informational, not medical diagnosis
    or treatment.
-   Do not generate medical claims from user profile data or nutrition
    logs.
-   Allergy data must be explicit and must not be inferred from missing
    data.

------------------------------------------------------------------------

## 13. Frontend Integration Rules

The React/TypeScript frontend should consume the API rather than
duplicate backend business logic.

-   Define typed API request/response contracts.
-   Keep API calls in a consistent client/service layer.
-   Represent loading, empty, error, success, and retry states.
-   Treat AI results as candidates until accepted where required.
-   Show the food name, portion, nutrition basis, and relevant
    uncertainty clearly.
-   Allow users to correct food identity and quantity before saving.
-   Distinguish unavailable nutrient values from zero.
-   Support Bengali and English text without hardcoding locale-specific
    assumptions into domain logic.
-   Use accessible form labels, keyboard interactions, and meaningful
    error messages.
-   Do not store authoritative nutrition calculations only in frontend
    state.
-   Avoid exposing private image storage URLs or model internals.

Suggested major frontend areas: - Authentication and profile -
Dashboard - Food search/catalog - Image recognition and review - Meal
logging - Daily/weekly nutrition analytics - Goals and progress -
Preferences - Contribution/review UI (role-restricted) - Admin/data
management (staff-restricted)

------------------------------------------------------------------------

## 14. Testing Requirements

Every feature should include appropriate tests.

### Model tests

-   Required/optional field validation.
-   Uniqueness constraints.
-   Positive quantity and valid range checks.
-   Relationship ownership and deletion behavior.
-   Category/variant cycle prevention.
-   Daily summary uniqueness.

### Nutrition tests

-   Per-100-g scaling.
-   Serving-to-gram conversion.
-   Unknown nutrient propagation.
-   Decimal precision and rounding.
-   Recipe ingredient totals.
-   Cooked-weight normalization.
-   Nutrition snapshot stability after catalog changes.

### Recognition tests

-   Valid and invalid image inputs.
-   Empty detections.
-   Multiple food regions.
-   Candidate ranking.
-   Confidence validation.
-   Unknown food handling.
-   User correction/confirmation.
-   Portion estimate validation.
-   Model version traceability.

### API tests

-   Authentication requirements.
-   Object-level ownership and permission boundaries.
-   Valid/invalid serializer payloads.
-   Pagination and filters.
-   No cross-user data leakage.
-   Atomic meal-item creation and audit events.

### Dataset tests

-   Duplicate hashes.
-   License/provenance required fields.
-   Split leakage checks.
-   Annotation status transitions.
-   Contribution approval/rejection.

### Frontend tests

-   Typed API behavior.
-   Loading/error/empty states.
-   Recognition correction flow.
-   Nutrition display and unknown values.
-   Meal editing and summary refresh.
-   Accessibility for core flows.

Do not rely only on happy-path tests. Include invalid input, missing
data, race conditions where relevant, and permission failures.

------------------------------------------------------------------------

## 15. Coding Agent Workflow

For each task:

1.  **Understand:** Restate the requested behavior internally and locate
    relevant code.
2.  **Inspect:** Read existing models, serializers, services, tests,
    migrations, and frontend consumers.
3.  **Plan:** Identify impacted modules, API contracts, schema changes,
    and backwards-compatibility risks.
4.  **Implement minimally:** Make the smallest coherent change that fits
    the architecture.
5.  **Validate:** Add/update tests and run targeted checks.
6.  **Review:** Inspect the diff for security, data integrity,
    performance, and accidental scope expansion.
7.  **Report:** Summarize files changed, behavior added, migrations,
    tests run, and any remaining limitations.

### Agent must not

-   Invent existing files, routes, settings, environment variables, or
    packages.
-   Rewrite unrelated modules.
-   create duplicate models when a suitable model already exists.
-   Put all business logic into views, serializers, or model `save()`
    methods.
-   silently change nutrition history.
-   silently change public API response shapes.
-   run destructive database commands without explicit authorization.
-   delete migrations or rewrite migration history.
-   use fake nutrition values as production data.
-   claim ML accuracy or portion precision without measured evaluation.
-   store credentials in source code.
-   mark work complete without reporting tests and known limitations.

### When requirements are ambiguous

Prefer the safest reversible implementation. Ask one focused question if
a missing decision affects data integrity, privacy, or a breaking
API/schema change. Otherwise document the assumption and proceed
conservatively.

------------------------------------------------------------------------

## 16. Definition of Done

A task is complete only when applicable items below are satisfied:

-   [ ] Implementation follows the existing repository conventions.
-   [ ] Correct domain module owns the behavior.
-   [ ] Database relationships and constraints are correct.
-   [ ] Migrations are created when schema changes.
-   [ ] Serializers and API permissions are updated where necessary.
-   [ ] Frontend contracts and UI are updated where necessary.
-   [ ] Tests cover expected and failure paths.
-   [ ] Relevant test/lint/type-check commands pass, or failures are
    reported.
-   [ ] No secrets or private user data are exposed.
-   [ ] Nutrition source and calculation provenance are preserved.
-   [ ] Historical meal records remain stable.
-   [ ] Documentation is updated for architectural/API changes.

------------------------------------------------------------------------

## 17. Architecture Decision Log

The following decisions are the current baseline. Revisit them only with
a clear reason and update this file when changed.

  -----------------------------------------------------------------------
  ID                      Decision                Rationale
  ----------------------- ----------------------- -----------------------
  ADR-001                 Django + DRF backend,   Clear API/frontend
                          React + TypeScript      separation
                          frontend                

  ADR-002                 PostgreSQL as           Referential integrity
                          relational source of    and structured querying
                          truth                   

  ADR-003                 Food and FoodNutrition  Food identity is
                          are separate            distinct from nutrient
                                                  profiles

  ADR-004                 Nutrition records are   Traceability and
                          source-aware and        correction history
                          versioned               

  ADR-005                 Meal + MealItem are     Avoid duplicate
                          primary consumption     food-log truth
                          records                 

  ADR-006                 FoodLog is an           Preserve changes
                          audit/event history     without double-counting
                                                  consumption

  ADR-007                 Recognition session,    Different lifecycles
                          result, detection, and  and confidence
                          portion estimate are    semantics
                          separate                

  ADR-008                 AI predicts food;       Prevent model-generated
                          nutrition service       nutrition
                          calculates nutrients    hallucinations

  ADR-009                 Meal items preserve     Historical logs remain
                          nutrition snapshots     reproducible

  ADR-010                 Bangladesh food names   Local food coverage and
                          and variants are        preparation differences
                          first-class             

  ADR-011                 Dataset images require  Legal, quality, and
                          provenance and split    evaluation reliability
                          integrity               

  ADR-012                 Services own            Testability and
                          cross-model workflows   separation of concerns
  -----------------------------------------------------------------------

------------------------------------------------------------------------

## 18. Reference Documentation

Use official documentation as the primary source when implementing
framework-specific behavior:

-   Django models:
    https://docs.djangoproject.com/en/6.0/topics/db/models/
-   Django authentication customization:
    https://docs.djangoproject.com/en/6.0/topics/auth/customizing/
-   Django database constraints:
    https://docs.djangoproject.com/en/6.0/ref/models/constraints/
-   Django model indexes:
    https://docs.djangoproject.com/en/6.0/ref/models/indexes/
-   Django REST Framework serializer relations:
    https://www.django-rest-framework.org/api-guide/relations/
-   Mermaid class diagrams:
    https://mermaid.js.org/syntax/classDiagram.html
-   Mermaid ER diagrams:
    https://mermaid.js.org/syntax/entityRelationshipDiagram.html
-   USDA FoodData Central: https://fdc.nal.usda.gov/
-   Open Food Facts: https://world.openfoodfacts.org/

Check documentation against the versions actually installed in the
repository. Do not upgrade dependencies solely because a newer
documentation version exists.

------------------------------------------------------------------------

## 19. Final Instruction to Coding Agents

Treat this document as the architectural contract for MealSense, but
treat the repository as the source of truth for what is currently
implemented.

Before creating or modifying a class: 1. Search for an existing
equivalent. 2. Confirm its owning module. 3. Confirm the UML
relationship and lifecycle. 4. Confirm whether it is a database model,
service, serializer, or value object. 5. Preserve provenance,
permissions, and historical data integrity. 6. Add tests for the
behavior.

Prefer a small, correct, testable implementation over a broad but
incomplete abstraction. Keep the codebase aligned with the eight domain
modules and update this document whenever the architecture changes.
