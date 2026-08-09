# expect/actual vs injected interface

## Prefer injected interface when

- The service is replaceable in tests
- Business code should not know which platform implementation exists
- DI already wires implementations

## Prefer expect/actual when

- The API is a tiny primitive with identical call-site semantics
- There is no meaningful fake beyond the platform value itself
- You need compile-time guarantees per target

## Always

- Create the common contract first
- Ship Android and iOS (or JVM) actuals in the same migration batch when both targets exist
