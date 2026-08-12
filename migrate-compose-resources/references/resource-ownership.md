# Compose and Android resource ownership

Compose Multiplatform resources commonly live under
`src/<sourceSet>/composeResources`; Android resources commonly live under
`src/<sourceSet>/res`. Treat type/key pairs as the public identity and locale or
qualifier directories as variants of the same definition.

Move resources with the feature or provider-owned shared UI that gives them
meaning. Keep generic theme primitives in a design-system/core UI module. A
consumer import does not transfer ownership. Preserve the key, source-set
availability, locale coverage, file content, and generated-resource imports.
For values XML, extract only the reviewed element from every locale/qualifier
file and leave unrelated definitions in place. Move an entire file only when
the file itself is the resource definition (for example a drawable or font).
