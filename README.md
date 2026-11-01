# MealSense

Installable food logging PWA with a Django REST API. This is an early MVP build of the [MealSense PRD](./MealSense%20PRD.docx.pdf).

## Run locally

Use Python 3.12–3.14 and a recent Node.js version.

```bash
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python manage.py migrate
.venv/bin/python manage.py runserver 127.0.0.1:8000
```

In another terminal:

```bash
cd frontend
npm ci
npm run dev -- --host 127.0.0.1
```

Open `http://127.0.0.1:5173`. Create an account, add a food with reference values per 100 g, then log a meal. The frontend proxies `/api` to the backend during development.

## What works

- Registration, sign in/out, profile and daily targets.
- Private personal food entries; manual meal logging, editing and deletion.
- Server-side calorie/macronutrient calculation from reference values and confirmed grams. Meal items keep nutrient snapshots.
- Daily dashboard and seven-day history, with user timezone boundaries.
- Private image upload, owner-checked image access, and account deletion.
- Installable PWA shell, offline read snapshot, locally saved text draft, responsive layout, and light/dark theme.

Food values entered by users are marked `User supplied`. Verify them before relying on them. Nutrition values are estimates, not medical advice.

## Still to decide or build

- AI model/provider and license. Image upload works; recognition currently returns `MODEL_NOT_CONFIGURED` and the app gives manual entry. No model result is invented.
- Curated/licensed nutrition catalog and provenance. The app starts with an empty shared catalog.
- Offline mutation queue and sync conflict UI. Offline text drafts remain on this device, then can be submitted when online.
- AI model/provider and license. Image upload works; recognition currently returns `MODEL_NOT_CONFIGURED` and the app gives manual entry. No model result is invented.
- Curated/licensed nutrition catalog and provenance. The app starts with an empty shared catalog.
- Offline mutation queue and sync conflict UI. Offline text drafts remain on this device, then can be submitted when online.
- Production private object storage, image retention policy, PostgreSQL deployment, backups, observability, export, and API schema generation.

## Temporary cloud recognition switch

Until the trained model ships, meal-photo recognition can call a cloud vision API. This is a temporary measure; cloud suggestions are always reviewed and confirmed like any other output, and manual logging still works when the provider is off or fails.

```bash
export AI_PROVIDER=openai        # '' (off, default) | openai | gemini
export AI_VISION_MODEL=gpt-4o-mini      # optional; openai default gpt-4o-mini, gemini default gemini-2.5-flash
export OPENAI_API_KEY=...        # used when AI_PROVIDER=openai
export GEMINI_API_KEY=...        # used when AI_PROVIDER=gemini
export AI_TIMEOUT_SECONDS=30     # optional request timeout
```

- `AI_PROVIDER` empty keeps recognition unavailable (`MODEL_NOT_CONFIGURED`); the PWA stays manual-only. It is the only switch to change.
- Candidates are label suggestions with a confidence value; no portion or nutrient value is taken from a photo. Each candidate also carries `food_id` when it matched a catalog food the user can use.
- Provider failures set prediction `status=failed` with `error_code=PROVIDER_ERROR` and never block saving a meal manually.
- Keys are read from env only and are not logged. For the provider call the server makes a small downscaled JPEG copy of the photo (the stored original keeps full quality), so uploads still leave the device during recognition.
- Swapping to the in-house model later means replacing `core/services.py:recognize_with_provider`; the view and API shape stay unchanged.

## Architecture and design

`backend/core/` owns domain models, validation, nutrition math, and API endpoints. The database is authoritative. Set `DATABASE_URL=postgresql://user:password@host:5432/db` to use PostgreSQL. For production set `DJANGO_DEBUG=0`, `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`, and `DJANGO_CSRF_TRUSTED_ORIGINS`.

`frontend/src/design/tokens.css` defines semantic theme tokens. `frontend/src/design/ui.tsx` defines shared controls; `frontend/src/design/styles.css` contains their styles and responsive layout. Feature screens live under `frontend/src/features/`. Change tokens or primitives to restyle the app. A future Flutter app should consume the same `/api/v1/` contract and mirror semantic design tokens with Flutter-native widgets.

## Checks

```bash
cd frontend && npm run build
cd backend && .venv/bin/python manage.py test core
```
