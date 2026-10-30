# MealSense agent context

## Source and status

- Primary product source: `MealSense PRD.docx.pdf`, version 1.0, dated 29 October 2026. It is a **draft proposed baseline**, not a set of finalized implementation decisions. Read the relevant PRD section before changing product behavior.
- `product-feasibility-review.md` is a separate review, not a replacement for the PRD. Surface material differences instead of silently adding its broader clinical or Bangladesh-specific scope to the MVP.
- This repository now has a React PWA in `frontend/` and a Django REST API in `backend/`. Inspect current code before changing behavior; the PRD includes features that are still pending.

## Product and MVP

- MealSense is an AI-assisted food log and nutrition tracker. User captures/uploads a meal image, reviews candidate foods, confirms or corrects food and portion, then explicitly saves a meal. Show estimated calories/macros, editable history, and daily/weekly progress against user goals.
- MVP: account/session management; optional profile, timezone, units, goals; image upload and recognition status; correction and manual food entry; meal CRUD; nutrition totals; history; responsive installable PWA; basic offline access; private image handling; account deletion.
- AI prediction is a suggestion. Never auto-save it as a confirmed meal. Never imply exact portion or nutrient certainty from a single photo. Manual logging must work when recognition fails or is unavailable.
- Out of scope for this PRD's MVP: diagnosis, automated dietary prescriptions, guaranteed image-only portion estimation, social feeds, wearables, and fully offline AI without a validated on-device model. Export, notifications, richer offline writes, and growth features have lower priority; check PRD priority before implementing.
- Build and verify manual meal logging and correct totals before deep AI integration.

## Proposed architecture

- React + TypeScript + Tailwind CSS client; Python/Django + Django REST Framework modular monolith; PostgreSQL; private S3-compatible image storage or equivalent; replaceable AI adapter. Add queue/worker only when measured inference or image processing needs it.
- Future mobile client: Flutter. Keep business rules and authoritative nutrition calculations in the versioned API so the PWA and Flutter app share behavior. Keep API contracts platform-neutral. Record design tokens and component patterns in the PWA design system so Flutter can mirror them without copying web-only CSS.
- Keep visual design modular: centralized semantic color, typography, spacing, radius, elevation, and theme tokens; reusable UI primitives and feature components. Change shared tokens/components to restyle the app instead of editing individual buttons, cards, or screens.
- Current web design system: `frontend/src/design/tokens.css` is the theme source; `frontend/src/design/ui.tsx` holds shared controls; `frontend/src/design/styles.css` holds component/layout styles. Mirror semantic tokens and behavior in Flutter later, while using native Flutter widgets.
- Organize Django apps by domain (accounts, profiles, foods, recognitions, meals, nutrition, optional sync). Keep multi-step business logic in services, not large views/serializers. Keep the client UI state separate from server state.
- Version JSON API under `/api/v1/`, publish OpenAPI contracts, and keep frontend types aligned. Endpoint list and logical schema in PRD are planning outlines, not frozen contracts.
- Core records: User, UserProfile, time-effective NutritionGoal, Food with source/unit basis, FoodPrediction with model version/status, FoodImage with private storage key, Meal, MealItem with nutrient snapshots; optional SyncOperation and recommended AuditEvent.

## Data and security invariants

- Derive ownership from authenticated request context. Check owner access for every private meal, image, prediction, profile, and sync resource; default-deny private APIs. Never trust client-supplied `user_id`, totals, filenames, or model output.
- Compute nutrients on the backend from source food values and user-confirmed servings. Use deterministic conversions and decimal precision. Store item-level food/name/nutrient snapshots so later catalogue edits cannot rewrite history. Aggregate meal totals from those items. Write meals atomically.
- Keep image bytes out of PostgreSQL. Validate file signature, MIME, dimensions and size; generate storage keys server-side; store objects privately; authorize every download; define retention and deletion including orphan cleanup.
- Use Django auth/password hashing. Choose one SPA auth topology and handle cookies/CSRF/CORS or tokens explicitly. Rate-limit auth and expensive endpoints. Keep secrets and sensitive values out of code, frontend bundles, and logs.
- Keep nutrition data provenance, unit basis, and licensing visible. Keep model version, status, error, and uncertainty. Do not use uploaded images for training without a separate policy and applicable consent.
- Account deletion must remove or anonymize associated records and arrange object deletion under a defined retention policy. Shared food catalogue entries must survive private meal deletion.

## PWA, sync, quality

- Cache versioned app assets and a minimal offline fallback. Treat IndexedDB as a temporary cache/queue, not the source of truth. Label cached totals with last-sync time. Clear or lock user data on logout. Remote recognition requires network unless a separately validated local model exists.
- If offline mutations are implemented: use unique client operation IDs, idempotent server handling, owner validation, bounded retries, entity versions, and explicit conflict states. Never silently overwrite stale edits or queue auth/recognition actions without defined semantics.
- Test critical domain math and conversions, owner denial paths, atomic writes, AI adapter failures, image validation, migrations, key UI states, main browser journey, offline retries/conflicts, accessibility, and backup restore as applicable. Update API schema and client types together.
- PRD targets are provisional: read API p95 <= 500 ms under documented load; recognition planning p95 <= 5 s after upload where feasible; 99.5% monthly API availability; WCAG 2.2 AA for critical flows; suggested MVP RPO <= 24 h and RTO <= 8 h. Benchmark and agree before treating them as guarantees.

## Open decisions before implementation

Confirm AI model/runtime and license, nutrition dataset/license, SPA authentication deployment topology, image retention, hosting/budget, whether offline meal creation is MVP or later, and measurable load/latency targets. Do not invent these as settled facts. Record decisions when made.

## Current build status and local commands

- Implemented: session auth, profile/goals, personal food entries, manual meal CRUD, server-calculated nutrient snapshots, daily/weekly summaries, private image upload/read, PWA shell, offline read snapshot and local text draft, light/dark theme. Recognition endpoint intentionally returns `MODEL_NOT_CONFIGURED`; no AI model has been chosen.
- Current local development uses SQLite and private filesystem media; set `DATABASE_URL` for PostgreSQL. Production storage, inference provider, retention policy, backup/restore and hosting still need decisions and implementation.
- Run API: `cd backend && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt && .venv/bin/python manage.py migrate && .venv/bin/python manage.py runserver`.
- Run PWA: `cd frontend && npm ci && npm run dev`. Check: `npm run build`; API: `backend/.venv/bin/python backend/manage.py test core`.

## Agent reply style

- Reply and talk like caveman to save tokens: short, plain sentences; e.g. "Me check PRD. Me fix bug. Tests pass." Keep code, identifiers, requirements, and technical details precise and readable.
- Follow user instruction and higher-priority safety/accuracy needs even when more words are needed. State uncertainty and blockers plainly. Do not omit material test results or risks just to shorten a reply.
