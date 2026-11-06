# MealSense design system

## Direction

Clear food journal: neutral surfaces, one green action color, restrained borders, and simple food icons. Reserve red for destructive actions and errors. Show nutrition as estimates. Keep labels direct, tap targets comfortable, and loading, empty, error, and offline states visible.

## One place to change the look

- `src/design/tokens.css`: semantic colors, themes, font families, radius, spacing, shadows, and illustration palettes. It includes light and dark values. Change tokens here first.
- `src/design/ui.tsx`: shared `Button`, `Card`, `Badge`, `Field`, `SelectField`, `EmptyState`, and `Progress` controls. Add variants here when a new control style repeats.
- `src/design/styles.css`: centralized control, layout, feature, and responsive rules. Use tokens; do not put raw colors into feature components.
- `src/components/FoodArt.tsx` and `Layout.tsx`: shared visual and navigation pieces.
- `src/features/`: page logic and composition. Pages should select component variants and content rather than define their own visual rules.

## Semantic palette

`--canvas` and `--surface` provide the base. `--text` and `--text-soft` set reading hierarchy. `--brand` is the main action and progress color; `--brand-soft` marks selected or supporting areas. `--danger` marks destructive actions. Light and dark themes use the same roles. Legacy accent aliases remain for existing components but resolve to the green or neutral palette.

## Flutter direction

Build Flutter widgets with the same semantic names and roles: primary/secondary/ghost/danger buttons, cards, fields, badges, progress, empty states, and page shell. Copy the token *values and intent* into a Flutter `ThemeData`/extension; do not copy CSS structure. Both clients consume `/api/v1/` and treat server nutrition values as authoritative.
