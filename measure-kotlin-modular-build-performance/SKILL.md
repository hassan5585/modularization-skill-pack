---
name: measure-kotlin-modular-build-performance
description: Measure whether modularization improves or harms Gradle build isolation and developer feedback time using reproducible scenario capture and median comparison. Use before modularizing, after splitting a feature, when suspecting over-modularization, or to see which modules recompile after a UI-only change. Does not require Gradle Enterprise.
---

# Measure Kotlin Modular Build Performance

Capture comparable metrics for clean, no-change, domain, data, UI, and convention
scenarios. Warmups are excluded. Single runs are not significance claims.

## Non-goals

- Replacing architecture verification with performance gates.
- Requiring commercial Gradle Enterprise / build scans.
- Declaring wins from one noisy sample.

## Workflow

1. Copy [assets/build-metrics-config.example.json](assets/build-metrics-config.example.json)
   and set explicit commands for the target repository.
2. Read [references/measurement-methodology.md](references/measurement-methodology.md)
   and [references/interpreting-build-metrics.md](references/interpreting-build-metrics.md).
3. Capture a baseline:

   ```bash
   python3 scripts/capture_gradle_build_metrics.py \
     --root /path/to/repo \
     --config .modularization/build-metrics-config.json \
     --output .modularization/build-metrics/baseline.json \
     --label baseline
   ```

4. After a modularization milestone, capture `current.json` the same way.
5. Compare:

   ```bash
   python3 scripts/compare_build_metrics.py \
     --baseline .modularization/build-metrics/baseline.json \
     --current .modularization/build-metrics/current.json \
     --json-out .modularization/build-metrics/comparison.json
   ```

6. Explain regressions via module granularity, dependency visibility, build logic,
   code generation, or platform coupling — never from a single run alone.

## Completion

Baseline and current artifacts exist, warmups are excluded, medians are reported,
environment mismatches are warned, and threshold failures are explicit.
