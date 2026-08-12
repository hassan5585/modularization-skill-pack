---
name: migrate-compose-resources
description: Audit and migrate Compose Multiplatform and Android string, drawable, image, font, XML, and other resources between Kotlin modules while preserving resource keys, localization variants, generated accessor visibility, ownership, and consumers. Use during feature/shared-ui extraction, when resource accessors stop resolving after module moves, when duplicate resources obscure ownership, or before removing a resource-owning module.
---

# Migrate Compose Resources

Treat resources as owned API, not incidental files. Move every locale/variant
together and preserve stable resource keys unless a rename is explicitly scoped.

## Workflow

1. Read [references/resource-ownership.md](references/resource-ownership.md).
2. Audit definitions and usages:

   ```bash
   python3 scripts/analyze_resources.py audit --root /path/to/repo \
     --json-out .modularization/resource-audit.json
   ```

3. Copy [assets/resource-migration-spec.example.json](assets/resource-migration-spec.example.json)
   and list reviewed moves using exact type, key, source module, and target module.
4. Plan:

   ```bash
   python3 scripts/analyze_resources.py plan --root /path/to/repo \
     --audit .modularization/resource-audit.json \
     --spec resource-migration-spec.json \
     --json-out .modularization/resource-migration-plan.json
   ```

5. Review ambiguous definitions and every consumer. Extract exact entries from
   shared values XML; move file-backed resources with reviewed hashes. Move all
   locale/qualifier variants in the same batch.
6. Update generated-resource imports without renaming keys. Compile the resource
   owner and all recorded consumers, then run `$verify-kotlin-modules`.

## Guardrails

- Do not rename or deduplicate resources during an ownership-only move.
- Do not copy a provider resource into each consumer.
- Keep feature/shared-UI resources with their semantic provider; promote only
  generic stable design-system resources to core UI.
- Stop when two definitions with the same type/key have different semantics.

## Completion

Complete when each moved definition has one owner, all variants and consumers
are accounted for, keys are unchanged, and generated accessors compile.
