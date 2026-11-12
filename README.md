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
- Meal-history sharing: a doctor without an account can request access using your email or phone; you approve, deny, or revoke it from the Sharing page, and approved doctors get 72 hours of read-only meal history and analytics (never photos, notes, or health metrics).
- Installable PWA shell, offline read snapshot, locally saved text draft, responsive layout, and light/dark theme.

Food values entered by users are marked `User supplied`. Verify them before relying on them. Nutrition values are estimates, not medical advice.

## Doctor access

Doctors have no accounts and do not need one. They open `/doctor` in the frontend,
enter the patient's email or phone, and the patient receives an in-app request on the
Sharing page to approve or deny. Approval generates a private access code that grants
read-only access for 72 hours, after which it expires automatically; the patient can
also revoke it at any time. The doctor copies the access code so they can reopen the
page later without repeating the request.

While access is active the doctor sees the meal history as a list plus analytics:
most-consumed foods, how often each food appears, monthly summaries, and any custom
date range. The view never exposes meal photos, personal notes, or health metrics
(weight, BMI, goals). An expired code answers as expired, and unmatched identifiers
receive the same generic reply, so the form cannot be used to confirm who has an
account.

The patient's own meal-history endpoint also accepts `from` and `to` date parameters.

## Still to decide or build

- Confirm model/dataset licensing and expand evaluation beyond the 19 trained food classes.
- Curated/licensed nutrition catalog and provenance. The app starts with an empty shared catalog.
- Offline mutation queue and sync conflict UI. Offline text drafts remain on this device, then can be submitted when online.
- Production private object storage, image retention policy, PostgreSQL deployment, backups, observability, export, and API schema generation.


## Recognition switch

Meal photo recognition supports the supplied BanglaFoodNet checkpoint on the backend.
The current local configuration uses the fine-tuned model, with CPU inference and no
cloud API calls. Suggestions still need confirmation; quantities and nutrition come
from the catalog and user-confirmed grams.

```bash
cd backend
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m pip install -r requirements-local.txt
cp .env.example .env
```

The model folder has been downloaded to `backend/model_artifacts/banglafoodnet/`.
For another checkout, download the contents of the
[shared Drive folder](https://drive.google.com/drive/folders/1RAlqpooPVkkW7pqyaYGcKgKkDrG7Yvxr)
into that directory. Large checkpoints and original notebooks are git-ignored.
See [model provenance](backend/model_artifacts.md) for checksums and model details.

```dotenv
AI_PROVIDER=local
AI_LOCAL_CHECKPOINT=model_artifacts/banglafoodnet/banglafoodnet_finetuned.pth
AI_LOCAL_DEVICE=cpu
```

Django loads `backend/.env` on startup. Existing environment variables take priority;
restart Django after editing it. Relative checkpoint paths resolve against `backend/`.
CPU dependencies are in `requirements-local.txt`; GPU deployments need a matching
CUDA build of PyTorch/Torchvision and `AI_LOCAL_DEVICE=cuda`.

- `AI_PROVIDER=local` uses the checkpoint's label order, image size, and dish weights.
  It returns up to five softmax-ranked suggestions and matches catalog foods the user
  can access. The loaded model is cached per backend process; the model version
  includes the checkpoint hash. Restart workers when replacing a checkpoint.
- The model classifies the whole photo into 19 known foods. It does not detect
  separate regions, estimate portions, or reject non-food/out-of-distribution images.
  Its component and ingredient heads are unused because they were not supervised.
- Missing files/dependencies return `unavailable`; invalid checkpoints or inference
  failures return `failed`. Manual logging stays available. Local failures never
  trigger a cloud fallback. Check server logs for load failures.
- An empty `AI_PROVIDER` turns recognition off (`MODEL_NOT_CONFIGURED`).
- `AI_PROVIDER=openai` with `OPENAI_API_KEY`, or `AI_PROVIDER=gemini` with
  `GEMINI_API_KEY`, selects the existing cloud adapter. `AI_VISION_MODEL` optionally
  overrides its default model and `AI_TIMEOUT_SECONDS` sets its request timeout.
  Cloud mode sends a downscaled JPEG to that provider. Keys stay in backend env.

## Architecture and design

`backend/core/` owns domain models, validation, nutrition math, and API endpoints. The database is authoritative. Set `DATABASE_URL=postgresql://user:password@host:5432/db` to use PostgreSQL. For production set `DJANGO_DEBUG=0`, `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`, and `DJANGO_CSRF_TRUSTED_ORIGINS`.

`frontend/src/design/tokens.css` defines semantic theme tokens. `frontend/src/design/ui.tsx` defines shared controls; `frontend/src/design/styles.css` contains their styles and responsive layout. Feature screens live under `frontend/src/features/`. Change tokens or primitives to restyle the app. A future Flutter app should consume the same `/api/v1/` contract and mirror semantic design tokens with Flutter-native widgets.

## Checks

```bash
cd frontend && npm run build
cd backend && .venv/bin/python manage.py test core
```
