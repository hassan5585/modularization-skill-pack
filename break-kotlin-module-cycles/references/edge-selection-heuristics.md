# Edge selection heuristics

Prefer cutting edges that:

1. Violate layer direction (e.g. data → ui).
2. Have clear file/import evidence.
3. Touch fewer consumers on the target side.
4. Align with stable ownership (feature vs core).
5. Minimize migration size for the next batch.

Deprioritize or reject cuts that:

- Create `shared-ui` → `shared-ui` edges
- Dump types into catch-all core/common modules
- Remove the only justified aggregation `api` facade without replacement
