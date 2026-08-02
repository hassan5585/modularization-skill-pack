# UI and design system

`core:ui` owns theme, spacing, shared widgets, responsive decisions, BaseViewModel, and cross-feature UI foundations. Feature UI modules own their screens, screen-specific widgets, UI models, formatters, and resources.

- Use app-window dimensions rather than physical device type.
- Preserve compact mobile behavior before adding two-pane/adaptive layouts.
- Keep dynamic list keys durable and provide content types for heterogeneous content.
- Keep frequently changing state reads late in layout/draw phases.
- Put visible strings in the owning module’s `composeResources/values/strings.xml`.
- Use Unicode punctuation and import every generated resource accessor explicitly.
- Prefer core widgets when available and keep Material use behind the design system as it grows.
- Label actionable/non-decorative icons and media for accessibility.
- Keep filled text fields and raw, inconsistent card styling out of feature code once design-system wrappers exist.
- Generate Compose compiler diagnostics with `-PcomposeCompilerReports=true` when investigating stability.

Do not globally mark Kotlin collections stable. Use immutable app-owned state/UI models and keep `compose_stability.conf` narrow.
