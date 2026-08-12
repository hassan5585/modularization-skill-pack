# Test ownership and source sets

Follow the source set of the production behavior:

| Production | Preferred test |
|---|---|
| `commonMain` | `commonTest` |
| `androidMain` | repository Android unit/host test source set |
| `iosMain` | `iosTest` or configured iOS test source set |
| `jvmMain` | `jvmTest` |

Keep a test next to the module that owns the subject. Put fakes, fixtures, and
builders in a feature/utility test-support module only when multiple owning
test modules consume them. Production modules must never depend on test-support.
Preserve coroutine dispatchers, fake behavior, fixtures, and assertion intent.
