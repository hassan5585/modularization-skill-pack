# Classification and boundary heuristics

## Contents

1. Evidence priority
2. Layer signals
3. Feature signals
4. Shared-code signals
5. Coupling and cycles
6. Confidence review

## 1. Evidence priority

Prefer evidence in this order:

1. Product and architecture documentation.
2. Navigation/entry-point structure and user-visible workflows.
3. Domain/API/database ownership.
4. Tests and DI registrations.
5. Package and directory names.
6. Class-name and import heuristics.

Scripts mainly use levels 5–6. An agent must reconcile them with levels 1–4.

## 2. Layer signals

### Domain

Positive signals:

- `model`, `entity` used as business vocabulary, `value`, `repository` interfaces, `usecase`, `policy`, `event`, `error`;
- interfaces whose methods expose domain types;
- pure Kotlin and standard/coroutines/time imports;
- deterministic logic with no framework construction.

Negative signals:

- HTTP annotations/clients, DTO suffixes, DAO/database annotations;
- UI toolkit, lifecycle/UI controllers, resources;
- navigation controller/graph implementation;
- Android/iOS platform types.

An interface is not automatically domain. A Retrofit service or DAO interface belongs to data.

### Data

Positive signals:

- `dto`, `request`, `response`, `remote`, `local`, `database`, `dao`, `cache`, `mapper`;
- concrete repository implementation;
- Ktor/Retrofit/OkHttp/GraphQL, Room/SQLDelight/Realm, preferences/data store;
- transport or persistence annotations.

Mappers returning UI models belong to UI or indicate a boundary leak; inspect manually.

### Navigation

Positive signals:

- destination/route contracts;
- graph builders, deep-link handlers, result keys;
- route argument serialization.

A screen setup function may stay in UI when it constructs UI types. Separate stable entry contracts from graph-to-screen adapters when helpful.

### UI

Positive signals:

- Composable/View/Fragment/Activity/Screen/Adapter;
- ViewModel/Presenter/Controller/UI state;
- UI resources, previews, themes, widgets;
- lifecycle and navigation UI imports.

Pure display formatting may be UI if it exists only to render a feature; business calculations remain domain.

### Shared UI

Treat `shared-ui` as an ownership/dependency decision, not a content heuristic.
Its files look like ordinary UI. Assign this layer only when:

- the file already belongs to a `:feature:<owner>:shared-ui` module; or
- reviewed evidence names a real feature UI consumer and preserves provider
  ownership.

Do not infer it from `shared`, `widget`, or `common` names. Record the consumer
UI → provider shared-UI edge explicitly and reject any provider shared-UI →
shared-UI chain.

The plan’s `shared_ui_violations` queue must be empty and
`plan_acceptance.shared_ui_graph` must be `pass` before migration begins.

### Test support

Positive signals:

- `Fake`, `Recording`, `Fixture`, `Mother`, `Builder`, deterministic clock/dispatcher;
- production-like source set used only from test configurations.

Actual `*Test` classes remain in the owning module’s test source set.

### Platform

Expect/actual implementations, Android services, iOS interop, JVM file/process adapters, and platform resource bridges belong in existing platform source sets or a cross-cutting `real` implementation module. Do not force them into shared domain.

For a KMP application framework, distinguish the deliberate Swift facade from
Kotlin-only platform implementation. Public declarations, `api` dependencies,
and native dependency exports are separate evidence: none alone proves that a
type belongs in the external Swift contract. Record accidental Objective-C
visibility as boundary debt rather than classifying it as a public platform API.

## 3. Feature signals

Strong feature candidates combine several of:

- a product term repeated across routes, screens, repositories, endpoints, and tests;
- a navigation subtree or independently reachable flow;
- data ownership with coherent CRUD/use cases;
- a stable set of user roles/permissions;
- cohesive release/change history;
- high internal imports and lower external imports.

Weak candidates:

- technical nouns (`ui`, `data`, `models`, `network`);
- generic suffixes (`impl`, `common`, `base`, `shared`);
- one-off screen names without owned behavior;
- package segments created only by framework conventions.

## 4. Shared-code signals

Candidate `core` code is stable, foundational, and broadly used. Candidate utilities express a replaceable capability behind a contract. Before extracting, ask:

- How many unrelated consumers exist now?
- Does the concept have one product owner?
- Does it change with one feature?
- Can consumers depend on a narrow contract instead?
- Will extraction reduce or merely hide coupling?

Prefer duplication of a tiny unstable helper over a premature shared abstraction.
For provider-owned presentation reuse, prefer an optional feature `shared-ui`
over moving business-specific UI to core. Keep generic design-system primitives
in core UI.

## 5. Coupling and cycles

Inspect:

- bidirectional package imports;
- repositories returning UI types;
- UI constructing concrete data implementations;
- navigation depending on screens and screens depending on graph internals;
- shared models importing feature-specific types;
- DI modules that expose implementation classes across features.

Break cycles at the semantic boundary:

- introduce a domain port;
- move an app-wide contract to core;
- depend on a navigation entry contract;
- invert a callback/event interface;
- split an overly broad model.

Do not solve cycles by moving both sides into `common`.

## 6. Confidence review

Treat script confidence as follows:

- `high`: path and content/import signals agree;
- `medium`: multiple content signals agree but ownership needs review;
- `low`: only names or a single import signal match;
- `unknown`: no reliable signal or conflicting strong signals.

Review all low/unknown files and all files with competing feature candidates before generating move manifests.
