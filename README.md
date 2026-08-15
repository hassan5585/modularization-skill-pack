# Portable Kotlin modularization skill pack

Twenty-three coordinated skills generate production-ready Kotlin Multiplatform
repositories or orchestrate, audit, design, extract foundations, scaffold,
migrate, integrate, decouple, and safely consolidate features and modules. The
pack includes focused DI, data, persistence, test, and Compose-resource boundary
workflows; optional Compose Navigation 2-to-3 migration; Destination route-key
standardization; cycle/platform/API remediation; build-performance measurement;
and architecture verification for Android, Kotlin Multiplatform, JVM, or mixed
Kotlin/Gradle repositories. The pack
supports optional feature-owned `shared-ui` modules without permitting
shared-UI dependency chains. For KMP projects it also guards the Kotlin/Native
dependency and Swift export surface, including generated framework headers.
Existing-project workflows preserve the target project’s libraries and generate
project-specific convention plugins instead of copying a reference stack.

Skills exchange versioned JSON artifacts under `.modularization/`
(`schema_version: 1`). Shared Python helpers live in `common/` and are installed
beside the skills.

## Skill map

```text
Existing repository
  -> audit-kotlin-architecture
  -> design-gradle-conventions
  -> extract-kotlin-foundations
  -> migrate-kotlin-feature  (scaffolds via scaffold-kotlin-feature)
      -> migrate-kotlin-data-boundaries / migrate-kotlin-persistence-boundaries
      -> migrate-kotlin-tests / migrate-compose-resources
      -> modularize-kotlin-dependency-injection
      -> integrate-kotlin-feature
  -> decouple-kotlin-features
  -> migrate-to-navigation3  (optional; only when Nav3 migration is requested)
  -> standardize-kotlin-destinations  (optional; Destination NavKey contract)
  -> break-kotlin-module-cycles
  -> extract-kmp-platform-boundaries
  -> harden-kotlin-module-apis
  -> verify-kotlin-modules
  -> measure-kotlin-modular-build-performance
  -> consolidate-kotlin-modules  (optional; evidence required)

New KMP repository
  -> create-kmp-repository
  -> scaffold-kotlin-feature
  -> extract-kmp-platform-boundaries / verify-kotlin-modules / …
```

Orchestration entry point for brownfield work: `$modularize-kotlin-codebase`.

## How to use this pack (as a user)

You do not need to memorize script flags. In an agent chat (Claude, Codex, Cursor,
Grok, etc.) install or invoke a skill by name and describe the outcome you want.
Prefer **one clear goal per turn**. The orchestrator and sibling skills will
propose plans, write reviewable artifacts under `.modularization/`, and ask before
destructive or irreversible steps.

| If you want… | Start with | Typical next skills |
|---|---|---|
| A brand-new Android+iOS KMP app | `$create-kmp-repository` | `$scaffold-kotlin-feature`, `$verify-kotlin-modules` |
| To modularize an existing monolith end-to-end | `$modularize-kotlin-codebase` | (coordinates all brownfield siblings) |
| Only a plan / inventory, no file moves | `$audit-kotlin-architecture` | optional `$measure-kotlin-modular-build-performance` |
| One new feature skeleton in a modular repo | `$scaffold-kotlin-feature` | `$verify-kotlin-modules` |
| To pull one existing feature out of the monolith | `$migrate-kotlin-feature` | `$break-kotlin-module-cycles`, `$verify-kotlin-modules` |
| To finish settings/app/DI/navigation wiring | `$integrate-kotlin-feature` | `$modularize-kotlin-dependency-injection`, `$verify-kotlin-modules` |
| To move or repair DI graphs/scopes/bindings | `$modularize-kotlin-dependency-injection` | `$integrate-kotlin-feature`, `$verify-kotlin-modules` |
| To remove undesirable acyclic feature coupling | `$decouple-kotlin-features` | `$migrate-compose-resources`, `$verify-kotlin-modules` |
| To move repositories, DTOs, serializers, or caches | `$migrate-kotlin-data-boundaries` | `$migrate-kotlin-persistence-boundaries`, `$harden-kotlin-module-apis` |
| To move tests, fixtures, or reusable fakes | `$migrate-kotlin-tests` | `$verify-kotlin-modules` |
| To move Compose/Android resources | `$migrate-compose-resources` | `$verify-kotlin-modules` |
| To move Room/SQLDelight/DataStore ownership | `$migrate-kotlin-persistence-boundaries` | `$migrate-kotlin-data-boundaries`, `$verify-kotlin-modules` |
| To merge evidence-backed over-fragmented modules | `$consolidate-kotlin-modules` | `$measure-kotlin-modular-build-performance`, `$verify-kotlin-modules` |
| To migrate Compose Navigation 2 → 3 | `$migrate-to-navigation3` | `$standardize-kotlin-destinations`, `$verify-kotlin-modules` |
| To adopt Destination route keys | `$standardize-kotlin-destinations` | `$verify-kotlin-modules` |
| To fix feature↔feature or layer cycles | `$break-kotlin-module-cycles` | `$verify-kotlin-modules` |
| To clean Android/iOS leaks out of `commonMain` | `$extract-kmp-platform-boundaries` | `$verify-kotlin-modules` |
| To shrink `api` edges / public Kotlin surface | `$harden-kotlin-module-apis` | `$audit-kotlin-native-framework` (if iOS) |
| To diagnose slow / huge iOS framework links | `$audit-kotlin-native-framework` | `$harden-kotlin-module-apis`, `$verify-kotlin-modules` |
| CI-style architecture guardrails | `$verify-kotlin-modules` | configure `.modularization/architecture-rules.json` |
| Proof modularization helped (or hurt) builds | `$measure-kotlin-modular-build-performance` | compare baseline vs after a milestone |

---

## Usage examples

Copy or adapt the prompts below. Replace product names, paths, and package IDs
with your own.

### 1. Install the pack into a repository

Use when this pack lives outside the app repo and you want repository-local
skills under `.agents/skills/`.

```bash
# From the skill-pack directory
python3 validate_skill_pack.py
python3 -m unittest discover -s tests -v

# Preview install
python3 install_skill_pack.py --target /path/to/repository

# Apply
python3 install_skill_pack.py --target /path/to/repository --apply
```

**Agent prompt:**

> Install the modularization skill pack into `/path/to/my-app` with a dry-run
> first, then apply if the preview looks correct.

---

### 2. Greenfield: create a new KMP mobile repository

Use when you want a working modular Android+iOS app from scratch (not a clone of
product code). The skill asks only for **app name**, **absolute destination**,
and **reverse-DNS package**.

**Agent prompt:**

> Use `$create-kmp-repository` to create a new KMP app named “Focus Garden” at
> `/Users/me/dev/focus-garden` with package `com.example.focusgarden`. Preview
> first, then apply. After generation, run the cheap verification steps and
> summarize what was created.

**What you get:** Compose Multiplatform shell, core layers, convention plugins,
dev/prod variants, a Home feature, test foundations, docs, CI, a narrow
`IosAppBridge`, and (by default) this whole skill pack installed into the new
repo.

**Then add product features:**

> Use `$scaffold-kotlin-feature` to add a `billing` feature with domain, data,
> navigation, and UI modules. Discover conventions from this repo, preview the
> scaffold, then apply with settings registration. Leave DI/nav wiring for me to
> review.

---

### 3. Brownfield: full modularization of an existing app

Use when you already have a Kotlin/Gradle app (Android, KMP, JVM, or mixed) and
want an incremental, behavior-preserving split into features + core + utils.

**Agent prompt (recommended entry):**

> Use `$modularize-kotlin-codebase` on this repository. Establish a baseline,
> audit architecture, propose feature boundaries for review, then stop before any
> structural edits so I can approve the plan.

After you approve the plan:

> Continue modularization. Design convention plugins, extract only foundations
> needed by the pilot, migrate the pilot feature dependency-first, and keep the
> build green after each batch. Track progress in `.modularization/`.

**What the orchestrator coordinates (in order):**

1. `$audit-kotlin-architecture` — inventory + plan  
2. `$design-gradle-conventions` — project-specific convention plugins  
3. `$extract-kotlin-foundations` — core / util / test foundations  
4. `$migrate-kotlin-feature` (+ `$scaffold-kotlin-feature`) — one vertical slice  
5. `$break-kotlin-module-cycles` / `$extract-kmp-platform-boundaries` as needed  
6. `$harden-kotlin-module-apis` + `$verify-kotlin-modules`  
7. optional `$measure-kotlin-modular-build-performance` and  
   `$audit-kotlin-native-framework` for KMP Apple frameworks  

Artifacts live under `.modularization/` (`audit.json`, `plan.json`,
`work-state.json`, `worklog.md`, …). Resume from the ledger instead of
re-discovering completed work.

---

### 4. Plan only: “What should our modules look like?”

Use when you want evidence and a proposed graph **without** moving code yet.

**Agent prompt:**

> Use `$audit-kotlin-architecture` on this repo. Produce `.modularization/audit.*`
> and a reviewed `plan.md`. Highlight feature candidates, cycles, high-coupling
> hotspots, and a recommended pilot feature. Do not edit production sources.

Optional performance baseline at the same time:

> Also capture a modularization build-metrics baseline with
> `$measure-kotlin-modular-build-performance` so we can compare later.

---

### 5. Extract one existing feature from the monolith

Use after an audit (or when you already know the feature name and ownership).

**Agent prompt:**

> Use `$migrate-kotlin-feature` to extract the `orders` feature. Scaffold target
> modules if missing, move domain → data → navigation → UI in small compilable
> batches, keep temporary adapters named and tracked, and run
> `$verify-kotlin-modules` after each batch. Do not migrate other features.

If the agent hits a cycle:

> Detect cycles with `$break-kotlin-module-cycles`, propose the best edge to cut
> with evidence, wait for my approval, apply one cut, re-verify, then resume
> `orders` migration.

---

### 6. Add a feature to an already modular repo

Use when the architecture is already layered and you need **new** modules, not
monolith extraction.

**Agent prompt:**

> Scaffold a `community` feature with domain, data, navigation, UI, and a
> provider-owned `shared-ui` because the feed card will be reused by chat.
> Use `$scaffold-kotlin-feature`, preview paths, then apply. Do not invent
> cross-feature shared-UI chains.

Without shared UI:

> Scaffold an `settings` feature with the standard four layers only (no
> shared-ui, no test module yet).

---

### 7. Fix “features depend on each other” / Gradle cycles

**Agent prompt:**

> Our `:feature:billing:ui` and `:feature:care:ui` form a cycle and block
> compilation. Use `$break-kotlin-module-cycles` to detect SCCs, explain the
> edges with file evidence, and propose a cut plan. Do not invent an event bus
> or dump types into core without review.

---

### 8. Clean platform code out of portable source sets

**Agent prompt:**

> `commonMain` imports Android and UIKit types in several modules. Use
> `$extract-kmp-platform-boundaries` to audit source-set leaks, plan extraction
> (expect/actual vs injected interfaces), and apply only the reviewed moves.
> Prefer util modules for platform services.

---

### 9. Shrink public API surface and accidental `api` edges

**Agent prompt:**

> Use `$harden-kotlin-module-apis` to audit project `api` dependencies and public
> implementation types. Propose narrowing to `implementation` where safe, mark
> implementation classes `internal`, and list any true public contracts that must
> stay. Then run `$verify-kotlin-modules`.

For KMP apps that ship an Apple framework, follow with:

> Audit the generated framework with `$audit-kotlin-native-framework` against our
> rules. Fail if the header grew, forbidden symbols appear, or dependency exports
> crept in.

---

### 10. Diagnose slow or OOM iOS framework linking

**Agent prompt:**

> `linkReleaseFrameworkIosArm64` is slow / memory-heavy. Use
> `$audit-kotlin-native-framework` on the latest linked framework (prefer an
> existing artifact before another release link). Check header size, forbidden
> exports, `framework.export`, and disabled compiler phases. Recommend a narrow
> Swift bridge and Gradle fixes without disabling DCE/Devirtualization.

---

### 11. Continuous architecture verification

Use after scaffolds/migrations, in PR review, or as a local pre-push habit.

**Agent prompt:**

> Configure `.modularization/architecture-rules.json` from the example if needed,
> then run `$verify-kotlin-modules`. Report layer violations, bad import
> directions, shared-UI chains, production→test leaks, cycles, and unapproved
> `api` edges. Suggest the narrowest Gradle compile/test commands for the
> changed modules.

**Manual static check (once rules exist):**

```bash
python3 verify-kotlin-modules/scripts/check_architecture.py \
  --root /path/to/repo \
  --rules /path/to/repo/.modularization/architecture-rules.json \
  --json-out /path/to/repo/.modularization/architecture-findings.json
```

---

### 12. Measure whether modularization improved build isolation

**Agent prompt:**

> Capture a baseline with `$measure-kotlin-modular-build-performance` (clean,
> no-change, domain, data, UI, convention scenarios). After we finish the pilot
> feature migration, capture `current` and compare medians. Call out environment
> mismatches and do not treat a single noisy run as proof.

---

### 13. Resume interrupted modularization work

**Agent prompt:**

> Resume `$modularize-kotlin-codebase` from `.modularization/work-state.json`.
> Revalidate the current HEAD and dirty tree against the last recorded baseline,
> finish any `in_progress` chunk, then continue with the next pending chunk. Do
> not re-run completed discovery or re-move completed files.

---

### 14. Migrate Compose Navigation 2 to Navigation 3

Use only when Navigation 3 migration is **explicitly** requested. Greenfield
apps from `$create-kmp-repository` already use Navigation 3.

**Agent prompt:**

> Use `$migrate-to-navigation3` on this repository. Run `audit` and `plan`, stop
> for review of `.modularization/navigation3-spec.json`, then scaffold the
> app-owned Navigator (preview first). Do not rewrite NavHost automatically.
> Preserve route identity; use our existing route base type or `NavKey` — do not
> invent a `Destination` type during Nav3 migration. After ViewModels use
> Navigator, plan an atomic NavDisplay cutover and run `check`. Then use
> `$standardize-kotlin-destinations` if we want the Destination convention.

**What you get:** inventory of Nav2 usage, a reviewed migration spec, optional
Navigator/options/recording-fake scaffold, and a post-migration residual check.
Kotlin host rewrites stay agent-driven.

---

### 15. Adopt Destination route contracts

Use on an already-Nav3 app (or after `$migrate-to-navigation3`) when the
repository should match the `$create-kmp-repository` Destination convention.
Greenfield apps already have Destination.

**Agent prompt:**

> Use `$standardize-kotlin-destinations` on this repository. Run `audit` and
> `plan`, stop for review of `.modularization/destination-spec.json`, then
> scaffold `Destination.kt` if it is missing (preview first). Convert existing
> `AppRoute` / `Screen` types onto Destination without changing serial names.
> Keep parameters primitive. Register serializers explicitly. Run `check`.

**What you get:** inventory of route keys, a reviewed destination-spec, optional
`Destination` + serializer-stub scaffold, and a convention check. Feature
destination rewrites stay agent-driven.

---

### 16. Focused boundary and integration workflows

**Finish a scaffolded feature:**

> Use `$integrate-kotlin-feature` for `orders`. Audit settings, app dependencies,
> DI, navigation, serializers, and app-shell registration; plan missing surfaces,
> apply only reviewed wiring, then run `check` and app verification.

**Move a complex data feature:**

> Use `$migrate-kotlin-data-boundaries` to snapshot repository and wire contracts,
> `$migrate-kotlin-persistence-boundaries` for Room/SQLDelight/DataStore code,
> `$migrate-kotlin-tests` for tests/fakes, and `$migrate-compose-resources` for UI
> resources. Preserve every wire, schema, stored-key, and resource identity.

**Remove cross-feature implementation coupling:**

> Use `$decouple-kotlin-features` to classify every production cross-feature
> edge. Propose provider shared UI, navigation/domain contracts, ports/events, or
> an exact reviewed allowance without inventing a catch-all core module.

**Repair graph ownership after module moves:**

> Use `$modularize-kotlin-dependency-injection`; preserve the detected DI
> framework, scopes, qualifiers, multibinding keys, assisted parameters, and
> platform graph entry points.

**Consolidate an over-fragmented graph:**

> Use `$consolidate-kotlin-modules` only with build/coupling evidence. Simulate
> the replacement graph, preserve public/resource/schema/native contracts, and
> compare the same build-metric scenarios afterward.

---

### 17. Common multi-skill playbooks (pick one goal)

**“We have a monolith and want a pilot only.”**

```text
$audit-kotlin-architecture
  -> review plan + choose pilot
  -> $design-gradle-conventions (if conventions are missing)
  -> $extract-kotlin-foundations (only what the pilot needs)
  -> $migrate-kotlin-feature (pilot)
  -> focused data/persistence/test/resource/DI skills as evidenced
  -> $integrate-kotlin-feature
  -> $verify-kotlin-modules
```

**“Greenfield app, then grow by feature.”**

```text
$create-kmp-repository
  -> $scaffold-kotlin-feature (repeat)
  -> $verify-kotlin-modules
  -> $audit-kotlin-native-framework (after public/iOS bridge changes)
```

**“Nav3 host is done; adopt Destination keys.”**

```text
$migrate-to-navigation3 (if still on Nav2)
  -> $standardize-kotlin-destinations
  -> $verify-kotlin-modules
```

**“Release readiness for a KMP app shell.”**

```text
$harden-kotlin-module-apis
  -> $verify-kotlin-modules (native_framework rules on)
  -> $audit-kotlin-native-framework (existing .framework / header)
```

**“Something feels over-modularized; builds got worse.”**

```text
$measure-kotlin-modular-build-performance (baseline vs current)
  -> $audit-kotlin-architecture (hotspots / fan-out)
  -> $harden-kotlin-module-apis (accidental api / export edges)
  -> $consolidate-kotlin-modules (only with reviewed evidence)
```

**“PR review: did this feature respect the architecture?”**

```text
$verify-kotlin-modules
  -> $check style of changed modules via suggested Gradle tasks
  -> if shared UI was added: confirm provider before consumers, no shared-UI chains
```

---

### 18. What *not* to ask these skills to do

These skills **preserve** the target project’s UI, DI, networking, persistence,
navigation, serialization, and test stack unless you explicitly request a
library change. Prefer other product skills for:

- product features, copy, or design-system polish unrelated to module shape;
- release signing, store upload, or secret/config injection;
- inventing event buses, catch-all `core` dumping grounds, or shared-UI
  dependency chains to “fix” cycles;
- disabling Kotlin/Native Devirtualization/DCE or exporting every module to Swift
  as a linker workaround.

Scripts that mutate the tree are **preview-by-default** (`--apply` only after
review). Cycle and architecture checkers **report and plan**; they do not
autonomously invent abstractions.

---

## Validate and install (pack maintainers)

Validate without third-party Python packages:

```bash
python3 validate_skill_pack.py
python3 -m unittest discover -s tests -v
```

Preview or install into a repository:

```bash
python3 install_skill_pack.py --target /path/to/repository
python3 install_skill_pack.py --target /path/to/repository --apply
```

For a greenfield Android+iOS app, start with `$create-kmp-repository`. It asks
for the app name, absolute destination, and reverse-DNS package name, then
previews and creates a working modular KMP repository with convention plugins,
dev/prod variants, a narrow iOS bridge, a representative feature, tests, CI,
documentation, repository-local skills, and verification tooling. Add further
product capabilities with `$scaffold-kotlin-feature`.

For an existing codebase, start with `$modularize-kotlin-codebase`. It
coordinates architecture discovery, convention-plugin creation, foundation
extraction, dependency-first feature and shared-UI chunks, cycle remediation,
platform-boundary cleanup, API hardening, optional build-performance baselines,
repository-local progress tracking, and static plus Gradle verification.
KMP projects that produce Apple frameworks also use
`$audit-kotlin-native-framework` before release verification and after changes
to public declarations, dependency visibility, or native interop.

## Skill reference (one-liners)

| Skill | One-line purpose |
|---|---|
| `create-kmp-repository` | Generate a production-shaped Android+iOS KMP repo from three inputs |
| `modularize-kotlin-codebase` | Orchestrate brownfield modularization with resumable tracking |
| `audit-kotlin-architecture` | Inventory the repo and propose a modularization plan |
| `design-gradle-conventions` | Extract/repeat Gradle setup into project convention plugins |
| `extract-kotlin-foundations` | Plan/scaffold core, util, and test foundations for the pilot |
| `scaffold-kotlin-feature` | Create empty layered feature modules in a modular repo |
| `migrate-kotlin-feature` | Move one real feature slice into those modules |
| `migrate-to-navigation3` | Audit/plan/scaffold/check Compose Navigation 2 → 3 migration |
| `standardize-kotlin-destinations` | Adopt Destination NavKey, destinationId, SerialName, and serializers |
| `break-kotlin-module-cycles` | Detect cycles and plan reviewed edge cuts |
| `extract-kmp-platform-boundaries` | Separate portable common code from platform implementations |
| `harden-kotlin-module-apis` | Narrow public Kotlin surface and accidental `api` edges |
| `audit-kotlin-native-framework` | Guard Swift-facing framework header and native build config |
| `verify-kotlin-modules` | Static architecture rules + suggested Gradle checks |
| `measure-kotlin-modular-build-performance` | Compare build isolation before/after structural change |
