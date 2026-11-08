# MealSense Liquid Glass Design System

## Direction

Apple Liquid Glass-inspired glassmorphism tailored to MealSense's organic emerald identity:
- **Continuous Full-Application Atmospheric SVG Backgrounds** (`public/bg-light.svg` and `public/bg-dark.svg`) rendered on `body::before` so the sidebar, navbar, modals, and main content share a single seamless canvas.
- **Floating Glass Sidebar (`GlassSidebar`)**: Vertically inset, rounded floating glass panel (`backdrop-filter: blur(var(--blur-xl)) saturate(var(--glass-saturate))`) with specular top highlight and layered depth.
- **Compact Liquid Glass Navbar (`GlassNavbar`)**: Minimal 52px height, translucent blurred surface, breadcrumb navigation, and compact meal-logging CTA.
- **Centralized Glass Primitives (`src/design/ui.tsx`)**: `GlassPanel`, `GlassCard` (`Card`), `GlassSidebar`, `GlassNavbar`, `GlassModal`, `GlassButton` (`Button`), `GlassInput` (`Field`), `GlassDropdown` (`SelectField`), `Badge`, `Progress`, and `EmptyState`.

## Architecture & Single Source of Truth

- `src/design/tokens.css`: Semantic colors, glass surface opacities, backdrop blur levels, specular borders, layered shadows, typography (`Outfit` display + `DM Sans` body), border radii, spacing, and transitions for both `:root` (Light Mode) and `[data-theme="dark"]` (Dark Mode).
- `src/design/ui.tsx`: Shared Liquid Glass UI primitives and controls.
- `src/design/styles.css`: Centralized component, layout, chart, modal, and responsive rules powered by CSS custom properties.
- `public/bg-light.svg` & `public/bg-dark.svg`: Responsive vector mesh backgrounds (`preserveAspectRatio="xMidYMid slice"`).
