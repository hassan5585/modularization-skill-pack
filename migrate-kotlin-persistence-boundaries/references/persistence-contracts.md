# Persistence contracts

Treat these as compatibility identities:

- Room database version, schema export, table and column names, entity primary
  keys, DAO query behavior, migration sequence, and platform database builder.
- SQLDelight database/schema name, table/column names, migration files, driver,
  and generated package.
- DataStore file name, preference key strings, serializer wire format, default
  values, and corruption/migration handlers.

An ownership-only move may change Kotlin packages and Gradle dependencies but
must not change those identities. Keep one schema owner. When a stored identity
must change, separate it into an explicit migration with upgrade/downgrade and
existing-install verification.
