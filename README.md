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
- Production private object storage, image retention policy, PostgreSQL deployment, backups, observability, export, and API schema generation.

## Architecture and design

`backend/core/` owns domain models, validation, nutrition math, and API endpoints. The database is authoritative. Set `DATABASE_URL=postgresql://user:password@host:5432/db` to use PostgreSQL. For production set `DJANGO_DEBUG=0`, `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`, and `DJANGO_CSRF_TRUSTED_ORIGINS`.

`frontend/src/design/tokens.css` defines semantic theme tokens. `frontend/src/design/ui.tsx` defines shared controls; `frontend/src/design/styles.css` contains their styles and responsive layout. Feature screens live under `frontend/src/features/`. Change tokens or primitives to restyle the app. A future Flutter app should consume the same `/api/v1/` contract and mirror semantic design tokens with Flutter-native widgets.

## Checks

```bash
cd frontend && npm run build
cd backend && .venv/bin/python manage.py test core
```
