# Native interop boundaries

- Keep Swift-facing API on a single app-owned bridge type.
- Do not place `platform.*` or cinterop types in feature `domain` modules.
- After public/native declaration changes, audit the generated Apple framework
  with `$audit-kotlin-native-framework`.
- Never disable Kotlin/Native Devirtualization or DCE to hide export mistakes.
