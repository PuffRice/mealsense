# MealSense design system

## Direction

Warm, calm food journal: soft neutral canvas, deep leaf green actions, rounded surfaces, gentle fruit and meal illustrations. Show nutrition as estimates. Prefer clear labels and encouraging, neutral language. Keep tap targets comfortable and give loading, empty, error, and offline states a visible message.

## One place to change the look

- `src/design/tokens.css`: semantic colors, themes, font families, radius, spacing, shadows, and illustration palettes. It includes light and dark values. Change tokens here first.
- `src/design/ui.tsx`: shared `Button`, `Card`, `Badge`, `Field`, `SelectField`, `EmptyState`, and `Progress` controls. Add variants here when a new control style repeats.
- `src/design/styles.css`: centralized control, layout, feature, and responsive rules. Use tokens; do not put raw colors into feature components.
- `src/components/FoodArt.tsx` and `Layout.tsx`: shared visual and navigation pieces.
- `src/features/`: page logic and composition. Pages should select component variants and content rather than define their own visual rules.

## Semantic palette

`--canvas` and `--surface` provide the base. `--text` and `--text-soft` set reading hierarchy. `--brand` is the main action color; `--brand-soft` is selection/background. `--accent` and `--accent-strong` mark progress. `--peach` and `--orange` mark secondary warmth. `--danger` marks destructive actions. Hero, scan, illustration, and auth palettes have their own named tokens to keep their special treatment themeable.

## Flutter direction

Build Flutter widgets with the same semantic names and roles: primary/secondary/ghost/danger buttons, cards, fields, badges, progress, empty states, and page shell. Copy the token *values and intent* into a Flutter `ThemeData`/extension; do not copy CSS structure. Both clients consume `/api/v1/` and treat server nutrition values as authoritative.
