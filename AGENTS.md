# MealSense agent context

## Source and status

- Primary product source: `MealSense PRD.docx.pdf`, version 1.0, dated 29 October 2026. It is a **draft proposed baseline**, not finalized implementation decisions. Read the relevant PRD section before changing product behavior.
- `product-feasibility-review.md` is a separate review, not a PRD replacement. Surface material differences instead of silently adding its broader clinical or Bangladesh-specific scope to the MVP.
- The repo has a React PWA in `frontend/` and a Django REST API in `backend/`. The PRD includes features still pending; PRD endpoint lists are planning outlines, not frozen contracts. Inspect current code before changing behavior.

## Product and MVP

- MealSense is an AI-assisted food log and nutrition tracker. User captures/uploads a meal image, reviews candidate foods, confirms or corrects food and portion, then explicitly saves a meal. Show estimated calories/macros, editable history, and daily/weekly progress against goals.
- MVP: account/session management; optional profile, timezone, units, goals; image upload and recognition status; correction and manual food entry; meal CRUD; nutrition totals; history; responsive installable PWA; basic offline access; private image handling; account deletion.
- AI prediction is a suggestion. Never auto-save it as a confirmed meal. Never imply exact portion or nutrient certainty from a single photo. Manual logging must work when recognition fails or is unavailable.
- Out of scope for this PRD's MVP: diagnosis, automated dietary prescriptions, guaranteed image-only portion estimation, social feeds, wearables, offline AI without a validated on-device model. Export, notifications, richer offline writes, and growth features are lower priority; check PRD priority before implementing.
- Build and verify manual meal logging and correct totals before deep AI integration.

## Actual structure (verified)

- Backend: Django 6 project `config/` with a **single app `core/`** — `core/models.py`, `serializers.py`, `services.py`, `views.py`, `urls.py`. There are no per-domain apps (accounts/foods/meals). Multi-step logic belongs in `core/services.py`, not views. New domains stay under `core` until splitting is warranted.
- API is versioned under `/api/v1/` and mounted via `backend/core/urls.py`. Endpoints: `auth/{csrf,register,login,logout}/`, `users/me/`, `foods/`, `meals/`, `meals/<uuid>/`, `nutrition/{daily,weekly}/`, `recognitions/`, `recognitions/<uuid>/`, `images/<uuid>/`.
- Auth is **session-cookie based** (DRF `SessionAuthentication`). CSRF is required: client fetches `/api/v1/auth/csrf/` and sends the token as `X-CSRFToken` on every unsafe request. Django test `Client` runs with `enforce_csrf_checks=True`, so tests must follow the same flow. Rate limits: 30/h anon, 300/h user (429s are expected, not bugs).
- `RecognitionsView` intentionally returns `MODEL_NOT_CONFIGURED`; no AI model has been chosen. Do not invent model results.
- Frontend: React 19 + TypeScript + Vite 8, Tailwind CSS v4 loaded via `@tailwindcss/vite` plugin (no tailwind config file; theme lives in `src/design/tokens.css` CSS variables). Lint is **oxlint** (`npm run lint`), formatting is **prettier** (`npm run format` / `format:check`), not ESLint.
- `npm run build` runs `tsc -b && vite build`, so build failure = type error. There is no separate typecheck script.
- Vite dev server proxies `/api` to `127.0.0.1:8000` (also in `preview`). Backend must run before frontend for API calls.
- PWA: `vite-plugin-pwa` in `vite.config.ts` (autoUpdate, precaches js/css/html/svg/png assets). App-level offline logic (read snapshot, text draft, theme) lives in `frontend/src/lib/offline.ts` + `localStorage`, keyed per user.
- SQLite (`backend/db.sqlite3`) and local private media (`backend/private_media/`, git-ignored) for dev; set `DATABASE_URL=postgresql://...` for PostgreSQL. Env vars: `DJANGO_DEBUG`, `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`, `DJANGO_CSRF_TRUSTED_ORIGINS`.
- Design system source of truth: `frontend/src/design/tokens.css` (semantic tokens incl. light/dark), `frontend/src/design/ui.tsx` (shared controls), `frontend/src/design/styles.css` (component/layout styles); see `frontend/DESIGN_SYSTEM.md`. Restyle by changing tokens/primitives, not editing individual screens. Future Flutter mirrors semantic tokens, not CSS.

## Commands

- API: `cd backend; python -m venv .venv; .venv/Scripts/pip install -r requirements.txt; .venv/Scripts/python manage.py migrate; .venv/Scripts/python manage.py runserver` — **this machine is Windows: use `.venv\Scripts\`**, not `.venv/bin/` (README shows POSIX).
- Tests: `backend\.venv\Scripts\python backend\manage.py test core` from repo root (or `cd backend` first). Full suite runs in minutes, no external services; image tests use Pillow-generated fixtures.
- Frontend: `cd frontend; npm ci; npm run dev`, check with `npm run build`, lint with `npm run lint`, format with `npm run format`.

## Data and security invariants

- Derive ownership from authenticated request context. Check owner access for every private meal, image, prediction, profile, and sync resource; default-deny private APIs. Never trust client-supplied `user_id`, totals, filenames, or model output (tests cover that client totals are ignored).
- Compute nutrients on the backend from source food values and user-confirmed servings. Deterministic conversions, decimal precision. Store item-level food/name/nutrient snapshots so later catalogue edits cannot rewrite history. Aggregate totals from those items. Post meal creation supports idempotent retries via client-supplied `operation_id`; keep that behavior.
- Keep image bytes out of PostgreSQL. Validate file signature, MIME, dimensions, size; generate storage keys server-side; store privately; authorize every download; define retention and deletion including orphan cleanup.
- Session cookies are HttpOnly/Samesite=Lax, Secure outside DEBUG; CSRF middleware is on. Keep secrets out of code, bundles, and logs.
- Keep nutrition provenance and unit basis visible; keep model version/status/error/uncertainty on recognitions. Do not use uploaded images for training without a separate policy and consent.
- Account deletion must remove or anonymize associated records and delete private media under a defined retention policy. Shared food catalogue entries survive private meal deletion.

## PWA, sync, quality

- Cache versioned app assets and a minimal offline fallback. IndexedDB/local storage is a temporary cache/queue, not the source of truth. Label cached totals with last-sync time. Clear or lock user data on logout. Remote recognition requires network.
- Offline mutations, if implemented: unique client operation IDs, idempotent server handling, owner validation, bounded retries, entity versions, explicit conflict states. Never silently overwrite stale edits or queue auth/recognition actions.
- Test critical domain math/conversions, owner denial paths, atomic writes, AI adapter failures, image validation, main browser journey, offline retries/conflicts, accessibility. Update API schema/serializers and frontend `lib/types.ts`/`lib/api.ts` together.
- PRD targets are provisional (API p95 ≤ 500 ms; recognition p95 ≤ 5 s; 99.5% availability; WCAG 2.2 AA; RPO ≤ 24 h / RTO ≤ 8 h). Benchmark and agree before treating as guarantees.

## Open decisions before implementation

AI model/runtime and license; nutrition dataset/license; production auth topology (currently dev-only session cookies); image retention; hosting/budget; offline meal creation MVP-or-later; measurable load/latency targets. Do not invent these as settled facts. Record decisions when made.

## Agent reply style

- Reply like caveman: short, plain sentences; e.g. "Me read PRD. Me fix bug. Tests pass." Keep code, identifiers, requirements, and technical details precise and readable.
- Follow user instructions and higher-priority safety/accuracy needs even when more words are needed. State uncertainty and blockers plainly. Do not omit material test results or risks just to shorten a reply.
