# Feature integration strategies

Integrate a feature through the narrowest existing app-owned surface:

1. Register all physical modules in Gradle settings.
2. Add app dependencies using the established aggregation root or explicit
   leaf modules; do not mix both without a documented reason.
3. Make bindings reachable through supported DI contribution/aggregation.
4. Register route serializers and graph entries explicitly where the repository
   requires them. Preserve route IDs, serial names, deep links, and result keys.
5. Add app-shell menus, tabs, registries, or entry points only when the product
   feature is intended to be directly reachable there.

Metro, Dagger/Hilt, Koin, and manual DI use different discovery rules. Treat a
missing graph contribution as a DI-boundary problem, not as justification for
public implementation modules. Navigation 2 and Navigation 3 likewise have
different hosts; follow detected repository patterns rather than converting
libraries during feature integration.
