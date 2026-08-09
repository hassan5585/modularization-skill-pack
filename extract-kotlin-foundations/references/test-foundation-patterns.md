# Test foundation patterns

## Repository-wide helpers

`:test` (or equivalent) holds production-independent helpers such as dispatcher
controllers and HTTP test clients. Sources live in the module’s **main** source
set but are consumed only from **test** configurations.

## Core-contract fakes

`:test:core` holds fakes for core ports once a second consumer appears.

## Feature test support

`feature/<name>/test` holds feature-owned fakes. Production modules must never
`implementation` these modules on main source sets; put them in
`test_dependencies` / `commonTest` only.
