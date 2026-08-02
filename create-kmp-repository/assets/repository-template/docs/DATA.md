# Data layer

Domain modules define repository interfaces and domain models. Data modules contain internal `Real*Repository` implementations, serializable request/response DTOs, mappers, persistence, network, and cache code.

Fallible operations return `KtResult<T, E>`, `EmptyResult<E>`, or a documented Flow contract. Preserve coroutine cancellation when mapping exceptions.

Use `safeCall`/`safeCallRaw` for Ktor responses. Do not call an HTTP client directly from UI/domain code, hardcode routes in repository bodies, or return response DTOs across the data boundary. Map response models to domain models.

Use `@Serializable` and explicit `@SerialName` on wire properties. Keep feature-owned DTOs in the owning data module; promote to core data only after multiple real feature consumers establish a stable wire concept.

Room databases, DAOs, schemas, migrations, and type converters live with their owning data boundary. Check schema JSON into source control and test pure migration decisions separately from platform integration.

Build `HttpClient` once through shared infrastructure with content negotiation, auth/logging as needed, and platform engines in `androidMain`/`iosMain`. Never commit endpoints or credentials; introduce environment values after product configuration is known.
