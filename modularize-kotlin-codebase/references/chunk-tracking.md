# Resumable chunk tracking

## Contents

1. Durable state
2. Chunk sizing
3. State transitions
4. Evidence and baseline failures
5. Decisions, risks, and temporary adapters
6. Resume protocol
7. Git checkpoints

## 1. Durable state

Keep machine state in `.modularization/work-state.json` and the generated review surface in `.modularization/worklog.md`. Treat JSON as authoritative and regenerate Markdown with `track_modularization.py validate`. Do not hand-edit either file while a tracker command can express the change.

The ledger must identify the initial branch/head and dirty files, every dependency-ordered chunk, exact verification results, architectural decisions, risks, and temporary compatibility adapters. Store repository-relative paths and no secrets.

## 2. Chunk sizing

A chunk must have one reviewable architectural purpose and a verification boundary. Good examples are:

- create and compile build conventions;
- convert one representative module to conventions;
- migrate one feature’s domain plus its tests;
- migrate one feature’s data layer plus repository tests;
- migrate and verify one provider feature’s shared UI before consumer UI;
- register one feature in DI/navigation/app aggregation;
- remove one named compatibility adapter;
- run full-slice verification.

Generate global shared-test or core/utility foundation chunks only when the reviewed plan names those targets. An empty `shared_foundation_modules` list means no shared-test-foundation chunk; ordinary feature-layer tests still belong to their owning modules. Do not make every feature depend on a speculative global foundation.

Split a chunk when it cannot be verified independently, mixes unrelated features, or leaves the repository in an unexplained non-compiling state. Do not create one chunk per file unless files truly have independent ownership and verification.

Represent each reviewed `consumer ui -> provider shared-ui` edge in the plan.
The tracker adds the provider shared-UI chunk as a dependency of the consumer UI
chunk even when feature ordering would otherwise place the consumer first.
Once a plan contains any shared-UI metadata, ledger initialization requires
`plan_acceptance.shared_ui_graph` to be explicitly `pass` and
`shared_ui_violations` to be empty; resolve architecture findings instead of
bypassing the gate. Legacy plans with no shared-UI metadata remain readable.

For a partially modularized repository, retain chunks for existing target modules but label them as validation/migration work. A directory or build file is not proof that the module is complete: verify conventions, registration, boundaries, source/artifact ownership, and tests before completing its chunk. Do not auto-complete historical structure from static discovery.

## 3. State transitions

Use only:

```text
planned -> in_progress -> completed
                      \-> blocked -> in_progress
planned/blocked -> skipped (explicit architectural reason only)
```

Keep at most one chunk `in_progress`. Complete dependencies before starting a child chunk. A skipped dependency satisfies ordering but must remain visible in the final review; never use skip to bypass required conventions, testing foundations, app wiring, or final verification.

## 4. Evidence and baseline failures

Run commands outside the tracker, then record the exact argv, exit code, concise outcome, and log/report artifact. Classify results as:

- `pass` — exit code zero and expected assertions/tasks ran;
- `pre-existing-failure` — reproduced before the migration and unchanged;
- `introduced-failure` — new or materially changed by the current work;
- `not-run` — blocked or unavailable, with a concrete reason.

Required introduced failures and required not-run checks block completion. A chunk with no executable check needs a precise `--no-check-reason` and reviewable evidence such as an approved mapping or diff.

## 5. Decisions, risks, and temporary adapters

Record decisions when ownership, layering, plugin decomposition, public API, or test-support placement is not mechanically determined. Record risks before touching route identity, serialization, schemas, generated code, resources, native exports, or reflection.

Every compatibility adapter needs a unique id, repository path, owner, and objective removal condition. Resolve it in the ledger when deleted. Final verification fails conceptually while any adapter is open unless the user explicitly approves it as retained architecture.

## 6. Resume protocol

On a new agent/session:

1. Read repository instructions and the ledger.
2. Run `track_modularization.py validate`.
3. Compare the current branch/head and dirty files with the active chunk’s start snapshot.
4. Inspect only the active/next chunk, its dependencies, decisions, risks, and open adapters.
5. Re-run the last narrow verification when the repository changed outside the recorded chunk.
6. Continue the active chunk or restart a blocked chunk; do not repeat completed moves.

If state and repository disagree, stop completion, record the discrepancy as a risk, and reconcile paths/build evidence first.

## 7. Git checkpoints

The ledger is repository-local even when commits are not authorized. When commits are authorized, prefer one compilable architectural checkpoint per commit and include the ledger update in the same commit. Never auto-commit from the tracker. Preserve unrelated dirty files and do not stage them with a migration chunk.
