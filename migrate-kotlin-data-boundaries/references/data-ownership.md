# Data ownership

- Domain owns repository ports and behavior-facing models.
- Feature data owns feature HTTP calls, request/response DTOs, serializers,
  mappers, caches, and concrete repository implementations.
- Shared data infrastructure may own HTTP wrappers, database infrastructure,
  serialization utilities, and wire models used by multiple independent
  features when semantic ownership is genuinely shared.
- Persistence entities, DAOs, drivers, and migrations require a separate schema
  review even when they ultimately live in a feature data module.

Preserve `@SerialName` values, default values, nullability, enum wire values,
polymorphic registrations, endpoint paths, error mapping, cache keys, and
invalidations. A class name or package can change without changing the wire;
the wire snapshot exists to prove that distinction.
