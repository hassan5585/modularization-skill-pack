"""Tests for the earlier architecture skill-pack expansion and shared helpers."""

from __future__ import annotations

import json
import stat
import sys
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

from helpers import PACK, PackTestCase, load_json, run, skill_script, write


class ArtifactSchemaTests(PackTestCase):
    def test_common_artifact_schema_validates_envelope(self) -> None:
        sys.path.insert(0, str(PACK))
        from common.artifact_schema import envelope_fields, validate_artifact

        payload = envelope_fields(skill="extract-kotlin-foundations", script="plan_foundations.py")
        payload["candidates"] = []
        payload["modules"] = []
        payload["migration_batches"] = []
        payload["plan_gates"] = {}
        self.assertEqual([], validate_artifact(payload, "foundation-plan"))
        self.assertTrue(validate_artifact({"schema_version": 2}, "generic"))


class ScaffoldKotlinFeatureTests(PackTestCase):
    def test_standard_four_layer_and_settings_registration(self) -> None:
        root = self.temporary / "repo"
        root.mkdir()
        write(root / "settings.gradle.kts", 'rootProject.name = "demo"\n')
        spec = load_json(PACK / "scaffold-kotlin-feature/assets/feature-spec.example.json")
        spec_path = self.temporary / "feature.json"
        spec_path.write_text(json.dumps(spec), encoding="utf-8")
        script = skill_script("scaffold-kotlin-feature", "scaffold_feature.py")
        preview = run(script, "--root", str(root), "--spec", str(spec_path))
        self.assertIn("Dry run", preview.stdout)
        self.assertFalse((root / "feature/orders/domain/build.gradle.kts").exists())
        run(
            script,
            "--root",
            str(root),
            "--spec",
            str(spec_path),
            "--register-settings",
            "--apply",
        )
        self.assertTrue((root / "feature/orders/domain/build.gradle.kts").is_file())
        settings = (root / "settings.gradle.kts").read_text()
        self.assertIn('":feature:orders:domain"', settings)
        # Idempotent second apply on settings only would conflict on build files
        run(script, "--root", str(root), "--spec", str(spec_path), "--apply", expected=3)

    def test_shared_ui_and_test_support_rules(self) -> None:
        root = self.temporary / "repo"
        root.mkdir()
        spec = load_json(
            PACK / "scaffold-kotlin-feature/assets/feature-spec-with-shared-ui.example.json"
        )
        path = self.temporary / "shared.json"
        path.write_text(json.dumps(spec), encoding="utf-8")
        script = skill_script("scaffold-kotlin-feature", "scaffold_feature.py")
        run(script, "--root", str(root), "--spec", str(path), "--apply")
        self.assertTrue((root / "feature/orders/shared-ui/build.gradle.kts").is_file())
        bad = json.loads(json.dumps(spec))
        bad["layers"]["shared-ui"]["dependencies"].append(
            'implementation(project(":feature:profile:shared-ui"))'
        )
        bad_path = self.temporary / "bad.json"
        bad_path.write_text(json.dumps(bad), encoding="utf-8")
        rejected = run(script, "--root", str(root), "--spec", str(bad_path), expected=2)
        self.assertIn("shared-ui must not depend on another shared-ui", rejected.stderr)

    def test_migrate_shim_delegates(self) -> None:
        root = self.temporary / "repo"
        root.mkdir()
        spec = load_json(PACK / "migrate-kotlin-feature/assets/feature-spec.example.json")
        path = self.temporary / "feature.json"
        path.write_text(json.dumps(spec), encoding="utf-8")
        run(
            skill_script("migrate-kotlin-feature", "scaffold_feature.py"),
            "--root",
            str(root),
            "--spec",
            str(path),
            "--apply",
        )
        self.assertTrue((root / "feature/orders/ui/build.gradle.kts").is_file())

    def test_discover_feature_conventions(self) -> None:
        root = self.temporary / "repo"
        write(
            root / "feature/home/domain/build.gradle.kts",
            'plugins { alias(libs.plugins.example.feature.domain) }\n'
            'kotlin { sourceSets.commonMain.dependencies { implementation(project(":core:domain")) } }\n',
        )
        write(
            root / "feature/home/domain/src/commonMain/kotlin/com/example/home/domain/X.kt",
            "package com.example.home.domain\nclass X\n",
        )
        out = self.temporary / "conventions.json"
        run(
            skill_script("scaffold-kotlin-feature", "discover_feature_conventions.py"),
            "--root",
            str(root),
            "--json-out",
            str(out),
        )
        data = load_json(out)
        self.assertEqual(1, data["schema_version"])
        self.assertEqual("home", data["features"][0]["name"])


class FoundationsTests(PackTestCase):
    def test_fan_in_alone_does_not_promote_feature_code(self) -> None:
        audit = {
            "schema_version": 1,
            "modules": [],
            "sources": [
                {
                    "path": "feature/billing/ui/InvoiceScreen.kt",
                    "package": "com.example.billing.ui",
                    "layer": "ui",
                    "feature": "billing",
                }
            ],
            "feature_coupling": [
                {"from": "orders", "to": "billing", "import_count": 9},
                {"from": "profile", "to": "billing", "import_count": 4},
                {"from": "care", "to": "billing", "import_count": 3},
            ],
        }
        audit_path = self.temporary / "audit.json"
        audit_path.write_text(json.dumps(audit), encoding="utf-8")
        out = self.temporary / "foundation-plan.json"
        run(
            skill_script("extract-kotlin-foundations", "plan_foundations.py"),
            "--audit",
            str(audit_path),
            "--json-out",
            str(out),
        )
        plan = load_json(out)
        # Feature path should not become a core module solely from coupling
        self.assertFalse(any(m["path"].startswith(":core:") and "billing" in m["path"] for m in plan["modules"]))
        self.assertTrue(
            any(
                c["ownership"] in {"feature-owned", "unresolved"}
                for c in plan["candidates"]
                if "billing" in c["path"] or c["path"].endswith("InvoiceScreen.kt")
            )
            or not any("InvoiceScreen" in c["path"] for c in plan["candidates"])
        )

    def test_scaffold_foundations_rejects_empty_catch_all_and_test_edges(self) -> None:
        root = self.temporary / "repo"
        root.mkdir()
        script = skill_script("extract-kotlin-foundations", "scaffold_foundations.py")
        catch_all = {
            "schema_version": 1,
            "platform": "kmp",
            "modules": [{"path": ":core:common", "package": "com.example.core.common"}],
        }
        path = self.temporary / "bad.json"
        path.write_text(json.dumps(catch_all), encoding="utf-8")
        rejected = run(script, "--root", str(root), "--spec", str(path), expected=2)
        self.assertIn("catch-all", rejected.stderr)
        empty = {
            "schema_version": 1,
            "platform": "kmp",
            "modules": [
                {
                    "path": ":core:domain",
                    "package": "com.example.core.domain",
                    "candidate_count": 0,
                }
            ],
        }
        path.write_text(json.dumps(empty), encoding="utf-8")
        rejected = run(script, "--root", str(root), "--spec", str(path), expected=2)
        self.assertIn("empty foundation", rejected.stderr)
        good = load_json(PACK / "extract-kotlin-foundations/assets/foundation-spec.example.json")
        # dry-run does not write
        path.write_text(json.dumps(good), encoding="utf-8")
        run(script, "--root", str(root), "--spec", str(path))
        self.assertFalse((root / "core/domain/build.gradle.kts").exists())
        run(script, "--root", str(root), "--spec", str(path), "--apply")
        self.assertTrue((root / "core/domain/build.gradle.kts").is_file())
        run(script, "--root", str(root), "--spec", str(path), "--apply", expected=3)


class CycleTests(PackTestCase):
    def test_detects_two_node_build_cycle_and_plans_cut(self) -> None:
        root = self.temporary / "repo"
        write(
            root / "feature/a/ui/build.gradle.kts",
            'dependencies { implementation(project(":feature:b:data")) }\n',
        )
        write(
            root / "feature/b/data/build.gradle.kts",
            'dependencies { implementation(project(":feature:a:ui")) }\n',
        )
        write(
            root / "feature/a/ui/src/main/kotlin/com/example/a/Ui.kt",
            "package com.example.a\nimport com.example.b.Data\nclass Ui\n",
        )
        write(
            root / "feature/b/data/src/main/kotlin/com/example/b/Data.kt",
            "package com.example.b\nimport com.example.a.Ui\nclass Data\n",
        )
        report_path = self.temporary / "cycle-report.json"
        result = run(
            skill_script("break-kotlin-module-cycles", "detect_module_cycles.py"),
            "--root",
            str(root),
            "--json-out",
            str(report_path),
            expected=1,
        )
        report = load_json(report_path)
        self.assertEqual(1, report["schema_version"])
        self.assertTrue(report["strongly_connected_components"])
        plan_path = self.temporary / "cycle-plan.json"
        run(
            skill_script("break-kotlin-module-cycles", "plan_cycle_breaks.py"),
            "--report",
            str(report_path),
            "--json-out",
            str(plan_path),
        )
        plan = load_json(plan_path)
        self.assertTrue(plan["candidate_cuts"])
        self.assertTrue(all(c.get("evidence") is not None or c.get("from") for c in plan["candidate_cuts"]))
        self.assertEqual("pass", plan["gates"]["no_shared_ui_chain_recommendation"])

    def test_scc_deterministic_order(self) -> None:
        sys.path.insert(0, str(PACK))
        from common.gradle_graph import strongly_connected_components

        graph = {
            ":c": [":a"],
            ":a": [":b"],
            ":b": [":c"],
            ":z": [":z"],
        }
        first = strongly_connected_components(graph)
        second = strongly_connected_components(graph)
        self.assertEqual(first, second)
        self.assertEqual([[":z"], [":a", ":b", ":c"]], first)


class PlatformBoundaryTests(PackTestCase):
    def test_flags_android_import_in_common_main(self) -> None:
        root = self.temporary / "repo"
        write(root / "shared/build.gradle.kts", 'plugins { id("org.jetbrains.kotlin.multiplatform") }\n')
        write(
            root / "shared/src/commonMain/kotlin/com/example/Bad.kt",
            "package com.example\nimport android.content.Context\nclass Bad\n",
        )
        write(
            root / "shared/src/androidMain/kotlin/com/example/Ok.kt",
            "package com.example\nimport android.content.Context\nclass Ok\n",
        )
        out = self.temporary / "platform.json"
        run(
            skill_script("extract-kmp-platform-boundaries", "audit_source_set_boundaries.py"),
            "--root",
            str(root),
            "--json-out",
            str(out),
            expected=1,
        )
        report = load_json(out)
        self.assertTrue(
            any(f["rule"] == "platform-import-in-portable-source-set" for f in report["findings"])
        )
        plan_out = self.temporary / "platform-plan.json"
        run(
            skill_script("extract-kmp-platform-boundaries", "plan_platform_extraction.py"),
            "--audit",
            str(out),
            "--json-out",
            str(plan_out),
        )
        plan = load_json(plan_out)
        self.assertTrue(plan["extractions"])
        self.assertIn("android_verification_listed", plan["gates"])


class ApiHardeningTests(PackTestCase):
    def test_public_implementation_and_api_edges(self) -> None:
        root = self.temporary / "repo"
        write(
            root / "feature/orders/data/build.gradle.kts",
            'dependencies { api(project(":feature:orders:domain")) }\n',
        )
        write(root / "feature/orders/domain/build.gradle.kts", "dependencies {}\n")
        write(
            root / "feature/orders/data/src/main/kotlin/com/example/orders/data/RealRepo.kt",
            "package com.example.orders.data\nclass RealRepo\n",
        )
        write(
            root / "feature/orders/domain/src/main/kotlin/com/example/orders/domain/Repo.kt",
            "package com.example.orders.domain\ninterface Repo\n",
        )
        out = self.temporary / "api.json"
        run(
            skill_script("harden-kotlin-module-apis", "audit_module_apis.py"),
            "--root",
            str(root),
            "--json-out",
            str(out),
        )
        report = load_json(out)
        self.assertTrue(any(f["rule"] == "api-project-dependency" for f in report["findings"]))
        self.assertTrue(
            any(
                d["name"] == "RealRepo" and d["classification"] == "implementation-detail"
                for d in report["declarations"]
            )
        )
        plan_out = self.temporary / "api-plan.json"
        run(
            skill_script("harden-kotlin-module-apis", "plan_dependency_visibility.py"),
            "--audit",
            str(out),
            "--json-out",
            str(plan_out),
        )
        plan = load_json(plan_out)
        self.assertTrue(
            any(c["kind"] in {"api-to-implementation", "public-to-internal"} for c in plan["changes"])
        )


class BuildMetricsTests(PackTestCase):
    def test_warmups_excluded_median_and_comparison(self) -> None:
        root = self.temporary / "repo"
        root.mkdir()
        runner = self.temporary / "fake_gradle.py"
        runner.write_text(
            "#!/usr/bin/env python3\n"
            "import os, sys\n"
            "n = int(os.environ.get('FAKE_RUN', '0')) + 1\n"
            "os.environ['FAKE_RUN'] = str(n)\n"
            # Capture script sets env per process — use file counter instead
            "counter = Path = __import__('pathlib').Path\n"
            "c = counter(__file__).with_suffix('.count')\n"
            "val = int(c.read_text()) if c.exists() else 0\n"
            "val += 1\n"
            "c.write_text(str(val))\n"
            "elapsed = {1: 9.0, 2: 5.0, 3: 4.0, 4: 6.0}.get(val, 5.0)\n"
            "print('METRICS_ELAPSED=%s' % elapsed)\n"
            "print('4 actionable tasks: 2 executed, 0 from cache, 1 up-to-date, 1 skipped')\n"
            "print('Configuration cache entry reused')\n"
            "sys.exit(0)\n",
            encoding="utf-8",
        )
        runner.chmod(runner.stat().st_mode | stat.S_IEXEC)
        # Simpler deterministic fake: always print fixed metrics with increasing counter via append file
        runner.write_text(
            "#!/usr/bin/env python3\n"
            "from pathlib import Path\n"
            "import sys\n"
            "c = Path(sys.argv[0]).with_suffix('.count')\n"
            "val = int(c.read_text()) if c.exists() else 0\n"
            "val += 1\n"
            "c.write_text(str(val))\n"
            "elapsed = {1: 10.0, 2: 4.0, 3: 6.0, 4: 5.0, 5: 8.0, 6: 7.0, 7: 9.0, 8: 5.5}.get(val, 5.0)\n"
            "print(f'METRICS_ELAPSED={elapsed}')\n"
            "print('4 actionable tasks: 2 executed, 0 from cache, 1 up-to-date, 1 skipped')\n"
            "print('Configuration cache entry reused')\n",
            encoding="utf-8",
        )
        runner.chmod(runner.stat().st_mode | stat.S_IEXEC)
        config = {
            "schema_version": 1,
            "warmups": 1,
            "measured_runs": 3,
            "scenarios": [{"id": "no-change", "command": ["./gradlew", "help"]}],
        }
        config_path = self.temporary / "metrics-config.json"
        config_path.write_text(json.dumps(config), encoding="utf-8")
        baseline = self.temporary / "baseline.json"
        run(
            skill_script("measure-kotlin-modular-build-performance", "capture_gradle_build_metrics.py"),
            "--root",
            str(root),
            "--config",
            str(config_path),
            "--output",
            str(baseline),
            "--label",
            "baseline",
            "--command-runner",
            str(runner),
        )
        data = load_json(baseline)
        scenario = data["scenarios"][0]
        self.assertEqual(1, len(scenario["warmups"]))
        self.assertTrue(scenario["warmups"][0]["excluded_from_metrics"])
        self.assertEqual(3, len(scenario["runs"]))
        self.assertIsNotNone(scenario["median_elapsed_seconds"])
        # Reset counter for current capture with different timings
        count_file = runner.with_suffix(".count")
        if count_file.exists():
            count_file.unlink()
        current = self.temporary / "current.json"
        # Make current slower medians by rewriting fake after first capture path —
        # use a second runner
        runner2 = self.temporary / "fake_gradle2.py"
        runner2.write_text(
            "#!/usr/bin/env python3\n"
            "from pathlib import Path\n"
            "import sys\n"
            "c = Path(sys.argv[0]).with_suffix('.count')\n"
            "val = int(c.read_text()) if c.exists() else 0\n"
            "val += 1\n"
            "c.write_text(str(val))\n"
            "elapsed = {1: 10.0, 2: 20.0, 3: 22.0, 4: 21.0}.get(val, 20.0)\n"
            "print(f'METRICS_ELAPSED={elapsed}')\n"
            "print('10 actionable tasks: 8 executed, 0 from cache, 1 up-to-date, 1 skipped')\n",
            encoding="utf-8",
        )
        runner2.chmod(runner2.stat().st_mode | stat.S_IEXEC)
        run(
            skill_script("measure-kotlin-modular-build-performance", "capture_gradle_build_metrics.py"),
            "--root",
            str(root),
            "--config",
            str(config_path),
            "--output",
            str(current),
            "--label",
            "current",
            "--command-runner",
            str(runner2),
        )
        comparison = self.temporary / "comparison.json"
        result = run(
            skill_script("measure-kotlin-modular-build-performance", "compare_build_metrics.py"),
            "--baseline",
            str(baseline),
            "--current",
            str(current),
            "--json-out",
            str(comparison),
            expected=1,
        )
        cmp_data = load_json(comparison)
        self.assertEqual("regression", cmp_data["comparisons"][0]["status"])
        self.assertEqual("fail", cmp_data["gates"]["thresholds"])

    def test_task_state_parsing_without_gradle(self) -> None:
        sys.path.insert(0, str(PACK / "measure-kotlin-modular-build-performance" / "scripts"))
        import capture_gradle_build_metrics as capture

        states = capture.parse_task_states(
            "BUILD SUCCESSFUL in 2s\n5 actionable tasks: 3 executed, 1 from cache, 1 up-to-date, 0 skipped\n"
        )
        self.assertEqual(5, states["actionable"])
        self.assertEqual(3, states["executed"])
        self.assertEqual(1, states["from_cache"])
        self.assertEqual(
            "reused",
            capture.parse_configuration_cache("Configuration cache entry reused.\n"),
        )


class ManifestIntegrationTests(PackTestCase):
    def test_manifest_has_twenty_three_unique_skills(self) -> None:
        manifest = load_json(PACK / "skill-pack.json")
        skills = manifest["skills"]
        self.assertEqual(23, len(skills))
        self.assertEqual(23, len(set(skills)))
        self.assertIn("migrate-to-navigation3", skills)
        self.assertIn("standardize-kotlin-destinations", skills)
        for name in skills:
            self.assertTrue((PACK / name / "SKILL.md").is_file())
            self.assertTrue((PACK / name / "agents" / "openai.yaml").is_file())
