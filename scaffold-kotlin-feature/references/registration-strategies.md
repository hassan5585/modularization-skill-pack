# Registration strategies

## Settings

Prefer explicit `include(":feature:name", ":feature:name:domain", ...)` entries.
`--register-settings` appends only missing includes and is safe to re-run.

Type-safe project accessors (`projects.feature.name.domain`) and string
`project(":feature:name:domain")` forms are both accepted in specs.

## App / DI / navigation

Do **not** auto-edit these unless the repository has a documented, machine-stable
pattern. Typical reviewed steps:

1. Add `implementation(project(":feature:name"))` (or type-safe accessor) on the app shell.
2. Register feature DI containers with the existing graph/container API.
3. Register navigation graphs beside other feature graphs.
4. Add destination serializers and preferences when the project requires them.

## Resources

Create Compose resource or Android `res` directories only when
`create_resource_directory` is true in the spec.
