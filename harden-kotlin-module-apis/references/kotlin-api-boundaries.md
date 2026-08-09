# Kotlin API boundaries

| Classification | Typical action |
|---|---|
| stable-contract | Keep public; ensure consumers depend on the owning module |
| aggregation-facade | May `api` own children when documented |
| implementation-detail | Prefer `internal` |
| wire-persistence-dto | Hide behind mappers; do not expose via domain |
| generated-api | Exclude from manual rewrites |
| swift-facing-bridge | Keep explicit and minimal |
| unresolved | Source review required |

Default Kotlin visibility is public — absence of a modifier is not “safe”.
