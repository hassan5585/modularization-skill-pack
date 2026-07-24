from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PACK = Path(__file__).resolve().parents[1]
PYTHON = sys.executable


def write(path: Path, text: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def run(script: Path, *args: str, cwd: Path | None = None, expected: int = 0) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        [PYTHON, str(script), *map(str, args)],
        cwd=cwd,
        text=True,
        capture_output=True,
        timeout=30,
    )
    if result.returncode != expected:
        raise AssertionError(
            f"expected exit {expected}, got {result.returncode}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    return result


class SkillPackTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = Path(tempfile.mkdtemp(prefix="modularization-pack-test-"))

    def tearDown(self) -> None:
        shutil.rmtree(self.temporary, ignore_errors=True)

    def test_pack_validates_without_optional_dependencies(self) -> None:
        result = run(PACK / "validate_skill_pack.py", str(PACK))
        self.assertIn("passed", result.stdout)
        convention_spec = json.loads((PACK / "design-gradle-conventions/assets/build-logic-spec.example.json").read_text())
        architecture_rules = json.loads((PACK / "verify-kotlin-modules/assets/architecture-rules.example.json").read_text())
        registered = {item["id"] for item in convention_spec["plugins"]}
        required = set(architecture_rules["conventions"]["required_registered_plugin_ids"])
        self.assertTrue(required.issubset(registered))

    def test_installer_uses_manifest_and_refuses_conflicts(self) -> None:
        target = self.temporary / "repository"
        target.mkdir()
        preview = run(PACK / "install_skill_pack.py", "--target", str(target))
        self.assertIn("Dry run: 5 skill(s)", preview.stdout)
        run(PACK / "install_skill_pack.py", "--target", str(target), "--apply")
        for name in json.loads((PACK / "skill-pack.json").read_text())["skills"]:
            self.assertTrue((target / ".agents" / "skills" / name / "SKILL.md").is_file())
        run(PACK / "install_skill_pack.py", "--target", str(target), "--apply", expected=3)

    def test_audit_excludes_unrelated_nested_build_and_prefers_module_ownership(self) -> None:
        root = self.temporary / "repo"
        write(root / "settings.gradle.kts", 'pluginManagement { includeBuild("build-logic") }\ninclude(":app", ":core:domain", ":feature:payments:domain", ":feature:payments:data", ":feature:payments:ui", ":feature:payments:test")\n')
        write(root / "build.gradle.kts")
        write(root / "app" / "build.gradle.kts", 'plugins { id("org.jetbrains.kotlin.jvm") }\n')
        write(root / "core" / "domain" / "build.gradle.kts", 'plugins { id("org.jetbrains.kotlin.jvm") }\n')
        write(root / "feature" / "payments" / "domain" / "build.gradle.kts", 'plugins { id("org.jetbrains.kotlin.jvm") }\n')
        write(root / "feature" / "payments" / "data" / "build.gradle.kts")
        write(root / "feature" / "payments" / "ui" / "build.gradle.kts")
        write(root / "feature" / "payments" / "test" / "build.gradle.kts")
        write(root / "build-logic" / "settings.gradle.kts", 'rootProject.name = "build-logic"\n')
        write(root / "build-logic" / "convention" / "build.gradle.kts", 'plugins { `kotlin-dsl` }\n')
        write(root / "sample" / "settings.gradle.kts", 'rootProject.name = "sample"\n')
        write(root / "sample" / "app" / "build.gradle.kts")
        write(root / "sample" / "app" / "src/main/kotlin/com/acme/sample/Sample.kt", "package com.acme.sample\nclass Sample\n")
        write(root / ".modularization" / "dry-run" / "build.gradle.kts")
        write(root / ".modularization" / "dry-run" / "src/main/kotlin/com/acme/fake/Fake.kt", "package com.acme.fake\nclass Fake\n")
        write(root / "app" / "src/main/kotlin/com/acme/orders/ui/OrdersScreen.kt", "package com.acme.orders.ui\nclass OrdersScreen\n")
        write(root / "app" / "src/main/AndroidManifest.xml", "<manifest />\n")
        write(root / "feature" / "payments" / "ui" / "src/main/res/values/strings.xml", "<resources />\n")
        write(root / "core" / "domain" / "src/main/kotlin/com/acme/profile/Profile.kt", "package com.acme.profile\ndata class Profile(val id: String)\n")
        write(root / "feature" / "payments" / "domain" / "src/main/kotlin/com/acme/odd/Money.kt", "package com.acme.odd\ndata class Money(val cents: Long)\n")
        audit_path = self.temporary / "audit.json"
        run(
            PACK / "audit-kotlin-architecture/scripts/audit_codebase.py",
            "--root", str(root), "--root-package", "com.acme", "--json-out", str(audit_path),
        )
        audit = json.loads(audit_path.read_text())
        self.assertEqual(".", audit["root"])
        self.assertEqual(8, audit["summary"]["module_count"])
        self.assertEqual(["build-logic"], audit["project"]["included_builds"])
        self.assertEqual(2, audit["summary"]["owned_artifact_count"])
        sources = {item["path"]: item for item in audit["sources"]}
        self.assertEqual("orders", sources["app/src/main/kotlin/com/acme/orders/ui/OrdersScreen.kt"]["feature"])
        self.assertIsNone(sources["core/domain/src/main/kotlin/com/acme/profile/Profile.kt"]["feature"])
        self.assertEqual("payments", sources["feature/payments/domain/src/main/kotlin/com/acme/odd/Money.kt"]["feature"])
        self.assertFalse(any(path.startswith("sample/") for path in sources))
        self.assertFalse(any(path.startswith(".modularization/") for path in sources))
        gradle_audit_path = self.temporary / "gradle-audit.json"
        run(
            PACK / "design-gradle-conventions/scripts/analyze_gradle_conventions.py",
            "--root", str(root), "--json-out", str(gradle_audit_path),
        )
        self.assertFalse(any(module["directory"].startswith(".modularization/") for module in json.loads(gradle_audit_path.read_text())["modules"]))

        plan_path = self.temporary / "plan.json"
        run(PACK / "audit-kotlin-architecture/scripts/plan_modules.py", "--audit", str(audit_path), "--json-out", str(plan_path))
        plan = json.loads(plan_path.read_text())
        self.assertEqual(["payments"], [feature["name"] for feature in plan["features"]])
        payments = plan["features"][0]
        self.assertTrue({":feature:payments:data", ":feature:payments:ui", ":feature:payments:test"}.issubset(payments["target_modules"]))
        self.assertEqual([], plan["testing"]["shared_foundation_modules"])
        self.assertTrue(any(item.get("feature") == "orders" for item in plan["unresolved"]))
        self.assertTrue(any(item["target"] == ":core:domain" for item in plan["retained_assignments"]))
        self.assertEqual(plan["artifact_accounting"]["audit_artifacts"], plan["artifact_accounting"]["accounted"])
        self.assertTrue(any(item["path"].endswith("AndroidManifest.xml") for item in plan["unresolved_artifacts"]))

    def test_feature_scaffold_places_support_dependencies_on_common_test(self) -> None:
        root = self.temporary / "repo"
        root.mkdir()
        spec = json.loads((PACK / "migrate-kotlin-feature/assets/feature-spec.example.json").read_text())
        spec_path = self.temporary / "feature.json"
        spec_path.write_text(json.dumps(spec), encoding="utf-8")
        run(PACK / "migrate-kotlin-feature/scripts/scaffold_feature.py", "--root", str(root), "--spec", str(spec_path), "--apply")
        data_build = (root / "feature/orders/data/build.gradle.kts").read_text()
        self.assertIn("sourceSets.commonMain.dependencies", data_build)
        self.assertIn("sourceSets.commonTest.dependencies", data_build)
        self.assertIn('project(":feature:orders:test")', data_build)
        aggregation = (root / "feature/orders/build.gradle.kts").read_text()
        self.assertNotIn(":feature:orders:test", aggregation)

    def test_shared_ui_scaffold_uses_ui_shape_and_rejects_inverted_edges(self) -> None:
        root = self.temporary / "repo"
        root.mkdir()
        spec = json.loads(
            (PACK / "migrate-kotlin-feature/assets/feature-spec-with-shared-ui.example.json").read_text()
        )
        spec_path = self.temporary / "feature-with-shared-ui.json"
        spec_path.write_text(json.dumps(spec), encoding="utf-8")
        result = run(
            PACK / "migrate-kotlin-feature/scripts/scaffold_feature.py",
            "--root", str(root), "--spec", str(spec_path), "--apply",
        )
        self.assertIn('":feature:orders:shared-ui"', result.stdout)
        shared_root = root / "feature/orders/shared-ui"
        self.assertTrue((shared_root / "build.gradle.kts").is_file())
        self.assertTrue(
            (shared_root / "src/commonMain/kotlin/com/example/orders/sharedui").is_dir()
        )
        self.assertTrue(
            (shared_root / "src/commonTest/kotlin/com/example/orders/sharedui").is_dir()
        )
        self.assertTrue((shared_root / "src/commonMain/composeResources").is_dir())
        self.assertIn(
            'project(":feature:orders:shared-ui")',
            (root / "feature/orders/ui/build.gradle.kts").read_text(),
        )
        self.assertIn(
            'project(":feature:orders:shared-ui")',
            (root / "feature/orders/build.gradle.kts").read_text(),
        )

        invalid = json.loads(json.dumps(spec))
        invalid["layers"]["shared-ui"]["dependencies"].append(
            "implementation(projects.feature.profile.sharedUi)"
        )
        invalid_path = self.temporary / "invalid-shared-ui.json"
        invalid_path.write_text(json.dumps(invalid), encoding="utf-8")
        rejected = run(
            PACK / "migrate-kotlin-feature/scripts/scaffold_feature.py",
            "--root", str(root), "--spec", str(invalid_path),
            expected=2,
        )
        self.assertIn("shared-ui must not depend on another shared-ui", rejected.stderr)

        outside_feature_root = json.loads(json.dumps(spec))
        outside_feature_root["layers"]["shared-ui"]["dependencies"].append(
            "implementation(projects.legacy.profile.sharedUi)"
        )
        outside_feature_root_path = self.temporary / "invalid-external-shared-ui.json"
        outside_feature_root_path.write_text(
            json.dumps(outside_feature_root),
            encoding="utf-8",
        )
        rejected = run(
            PACK / "migrate-kotlin-feature/scripts/scaffold_feature.py",
            "--root", str(root), "--spec", str(outside_feature_root_path),
            expected=2,
        )
        self.assertIn("shared-ui must not depend on another shared-ui", rejected.stderr)

        lower_layer = json.loads(json.dumps(spec))
        lower_layer["layers"]["domain"]["dependencies"].append(
            'implementation(project(path = ":feature:profile:shared-ui"))'
        )
        lower_path = self.temporary / "invalid-lower-layer.json"
        lower_path.write_text(json.dumps(lower_layer), encoding="utf-8")
        rejected = run(
            PACK / "migrate-kotlin-feature/scripts/scaffold_feature.py",
            "--root", str(root), "--spec", str(lower_path),
            expected=2,
        )
        self.assertIn("domain must not depend on feature shared-ui", rejected.stderr)

        feature_root = json.loads(json.dumps(spec))
        feature_root["layers"]["shared-ui"]["dependencies"].append(
            'implementation(project(":feature:orders"))'
        )
        feature_root_path = self.temporary / "invalid-shared-ui-root.json"
        feature_root_path.write_text(json.dumps(feature_root), encoding="utf-8")
        rejected = run(
            PACK / "migrate-kotlin-feature/scripts/scaffold_feature.py",
            "--root", str(root), "--spec", str(feature_root_path),
            expected=2,
        )
        self.assertIn("shared-ui must not depend on a feature root", rejected.stderr)

        foreign_contract = json.loads(json.dumps(spec))
        foreign_contract["layers"]["shared-ui"]["dependencies"].append(
            'implementation(project(":feature:profile:domain"))'
        )
        foreign_contract_path = self.temporary / "invalid-shared-ui-contract.json"
        foreign_contract_path.write_text(json.dumps(foreign_contract), encoding="utf-8")
        rejected = run(
            PACK / "migrate-kotlin-feature/scripts/scaffold_feature.py",
            "--root", str(root), "--spec", str(foreign_contract_path),
            expected=2,
        )
        self.assertIn(
            "shared-ui may depend only on its owner's feature contracts",
            rejected.stderr,
        )

        for label, dependency, expected_message in (
            (
                "data",
                'implementation(project(":feature:orders:data"))',
                "shared-ui must not depend on data",
            ),
            (
                "app",
                'implementation(project(":app"))',
                "shared-ui must not depend on app",
            ),
            (
                "test",
                "implementation(projects.feature.orders.test)",
                "shared-ui must not depend on test",
            ),
            (
                "test-core",
                'implementation(project(":test:core"))',
                "shared-ui must not depend on test-support",
            ),
        ):
            forbidden_target = json.loads(json.dumps(spec))
            forbidden_target["layers"]["shared-ui"]["dependencies"].append(dependency)
            forbidden_target_path = self.temporary / f"invalid-shared-ui-{label}.json"
            forbidden_target_path.write_text(
                json.dumps(forbidden_target),
                encoding="utf-8",
            )
            rejected = run(
                PACK / "migrate-kotlin-feature/scripts/scaffold_feature.py",
                "--root", str(root), "--spec", str(forbidden_target_path),
                expected=2,
            )
            self.assertIn(expected_message, rejected.stderr)

        test_consumer = json.loads(json.dumps(spec))
        test_consumer["layers"]["test"]["dependencies"].append(
            "implementation(projects.feature.profile.sharedUi)"
        )
        test_consumer_path = self.temporary / "invalid-test-to-shared-ui.json"
        test_consumer_path.write_text(json.dumps(test_consumer), encoding="utf-8")
        rejected = run(
            PACK / "migrate-kotlin-feature/scripts/scaffold_feature.py",
            "--root", str(root), "--spec", str(test_consumer_path),
            expected=2,
        )
        self.assertIn(
            "test must not depend on feature shared-ui",
            rejected.stderr,
        )

    def test_audit_plan_and_convention_analysis_preserve_optional_shared_ui(self) -> None:
        root = self.temporary / "repo"
        write(
            root / "settings.gradle.kts",
            'include(":feature:alpha", ":feature:alpha:domain", ":feature:alpha:navigation", '
            '":feature:alpha:shared-ui", ":feature:alpha:ui", ":feature:beta", '
            '":feature:beta:domain", ":feature:beta:navigation", ":feature:beta:ui")\n',
        )
        for module in (
            "feature/alpha",
            "feature/alpha/domain",
            "feature/alpha/navigation",
            "feature/alpha/ui",
            "feature/beta",
            "feature/beta/domain",
            "feature/beta/navigation",
        ):
            write(root / module / "build.gradle.kts")
        write(
            root / "feature/alpha/shared-ui/build.gradle.kts",
            'plugins { id("example.feature.ui") }\n',
        )
        write(
            root / "feature/beta/ui/build.gradle.kts",
            'dependencies { implementation(project(":feature:alpha:shared-ui")) }\n',
        )
        write(
            root / "feature/alpha/shared-ui/src/commonMain/kotlin/com/example/alpha/sharedui/AlphaCard.kt",
            "package com.example.alpha.sharedui\nclass AlphaCard\n",
        )
        write(
            root / "feature/beta/ui/src/commonMain/kotlin/com/example/beta/ui/BetaScreen.kt",
            "package com.example.beta.ui\n"
            "import com.example.alpha.sharedui.AlphaCard\n"
            "class BetaScreen(val card: AlphaCard)\n",
        )
        audit_path = self.temporary / "shared-ui-audit.json"
        run(
            PACK / "audit-kotlin-architecture/scripts/audit_codebase.py",
            "--root", str(root), "--root-package", "com.example", "--json-out", str(audit_path),
        )
        audit = json.loads(audit_path.read_text())
        alpha_card = next(
            item for item in audit["sources"] if item["path"].endswith("AlphaCard.kt")
        )
        self.assertEqual("shared-ui", alpha_card["layer"])
        self.assertEqual("high", alpha_card["layer_confidence"])

        plan_path = self.temporary / "shared-ui-plan.json"
        run(
            PACK / "audit-kotlin-architecture/scripts/plan_modules.py",
            "--audit", str(audit_path), "--json-out", str(plan_path),
        )
        plan = json.loads(plan_path.read_text())
        alpha = next(item for item in plan["features"] if item["name"] == "alpha")
        self.assertIn(":feature:alpha:shared-ui", alpha["target_modules"])
        self.assertEqual(
            [{
                "consumer": ":feature:beta:ui",
                "provider": ":feature:alpha:shared-ui",
                "source": "observed Gradle dependency",
            }],
            plan["shared_ui_dependencies"],
        )
        self.assertLess(
            plan["migration_layer_order"].index("shared-ui"),
            plan["migration_layer_order"].index("ui"),
        )
        self.assertEqual([], plan["shared_ui_violations"])
        self.assertEqual("pass", plan["plan_acceptance"]["shared_ui_graph"])

        gradle_audit = self.temporary / "shared-ui-gradle-audit.json"
        run(
            PACK / "design-gradle-conventions/scripts/analyze_gradle_conventions.py",
            "--root", str(root), "--json-out", str(gradle_audit),
        )
        modules = json.loads(gradle_audit.read_text())["modules"]
        shared = next(item for item in modules if item["path"] == ":feature:alpha:shared-ui")
        self.assertEqual("shared-ui", shared["role"])

        write(
            root / "feature/alpha/shared-ui/build.gradle.kts",
            'dependencies {\n'
            '  implementation(projects.feature.beta.sharedUi)\n'
            '  implementation(project(":feature:beta:domain"))\n'
            '  implementation(project(":test:core"))\n'
            '}\n',
        )
        write(
            root / "feature/beta/domain/build.gradle.kts",
            'dependencies { implementation(project(path = ":feature:alpha:shared-ui")) }\n',
        )
        invalid_audit_path = self.temporary / "invalid-shared-ui-audit.json"
        run(
            PACK / "audit-kotlin-architecture/scripts/audit_codebase.py",
            "--root", str(root), "--root-package", "com.example",
            "--json-out", str(invalid_audit_path),
        )
        invalid_plan_path = self.temporary / "invalid-shared-ui-plan.json"
        run(
            PACK / "audit-kotlin-architecture/scripts/plan_modules.py",
            "--audit", str(invalid_audit_path), "--json-out", str(invalid_plan_path),
        )
        invalid_plan = json.loads(invalid_plan_path.read_text())
        violation_ids = {
            item["rule"] for item in invalid_plan["shared_ui_violations"]
        }
        self.assertIn("shared-ui-to-shared-ui", violation_ids)
        self.assertIn("shared-ui-to-foreign-feature-contract", violation_ids)
        self.assertIn("lower-layer-to-shared-ui", violation_ids)
        self.assertIn("shared-ui-to-forbidden-layer", violation_ids)
        self.assertEqual("fail", invalid_plan["plan_acceptance"]["shared_ui_graph"])

    def test_audit_detects_android_groovy_and_kmp_capabilities(self) -> None:
        android = self.temporary / "android"
        write(android / "settings.gradle", "include ':app', ':core:domain'\n")
        write(
            android / "app/build.gradle",
            "plugins { id 'com.android.application' }\n"
            "dependencies {\n"
            "  implementation project(':core:domain')\n"
            "  implementation 'androidx.core:core-ktx:1.0.0'\n"
            "  testImplementation 'junit:junit:4.13.2'\n"
            "}\n",
        )
        write(android / "core/domain/build.gradle", "apply plugin: 'org.jetbrains.kotlin.android'\n")
        write(android / "build.gradle", "plugins { id 'org.jetbrains.kotlin.android' apply false }\n")
        write(android / "app/src/main/java/com/example/orders/ui/OrdersActivity.kt", "package com.example.orders.ui\nimport android.app.Activity\nclass OrdersActivity : Activity()\n")
        android_audit = self.temporary / "android-audit.json"
        run(PACK / "audit-kotlin-architecture/scripts/audit_codebase.py", "--root", str(android), "--root-package", "com.example", "--json-out", str(android_audit))
        android_data = json.loads(android_audit.read_text())
        self.assertTrue(android_data["project"]["detected"]["android"])
        app = next(module for module in android_data["modules"] if module["path"] == ":app")
        self.assertEqual([":core:domain"], app["project_dependencies"])
        self.assertIn("com.android.application", app["plugins"])
        self.assertTrue(any("androidx.core:core-ktx" in item["value"] for item in app["declared_dependencies"]))
        self.assertTrue(any("junit:junit" in item["value"] for item in app["declared_dependencies"]))
        root_module = next(module for module in android_data["modules"] if module["path"] == ":")
        self.assertNotIn("org.jetbrains.kotlin.android", root_module["plugins"])
        android_plan = self.temporary / "android-plan.json"
        run(PACK / "audit-kotlin-architecture/scripts/plan_modules.py", "--audit", str(android_audit), "--json-out", str(android_plan))
        self.assertEqual(["orders"], [item["name"] for item in json.loads(android_plan.read_text())["features"]])

        kmp = self.temporary / "kmp"
        write(kmp / "settings.gradle.kts", 'include(":shared")\n')
        write(kmp / "shared/build.gradle.kts", 'plugins { id("org.jetbrains.kotlin.multiplatform") }\nkotlin { iosArm64(); androidTarget() }\n')
        write(kmp / "shared/src/commonMain/kotlin/com/example/profile/Profile.kt", "package com.example.profile\nimport kotlinx.coroutines.flow.Flow\ninterface Profile { val values: Flow<String> }\n")
        write(kmp / "shared/src/iosMain/kotlin/com/example/platform/IosBridge.kt", "package com.example.platform\nimport platform.Foundation.NSObject\nclass IosBridge : NSObject()\n")
        kmp_audit = self.temporary / "kmp-audit.json"
        kmp_markdown = self.temporary / "kmp-audit.md"
        run(PACK / "audit-kotlin-architecture/scripts/audit_codebase.py", "--root", str(kmp), "--root-package", "com.example", "--json-out", str(kmp_audit), "--markdown-out", str(kmp_markdown))
        kmp_data = json.loads(kmp_audit.read_text())
        self.assertTrue(kmp_data["project"]["detected"]["kotlin_multiplatform"])
        self.assertIn("async", kmp_data["project"]["capabilities"])
        self.assertIn("IosBridge.kt", kmp_markdown.read_text())

    def test_shared_test_foundations_are_explicit_modules(self) -> None:
        root = self.temporary / "repo"
        root.mkdir()
        spec = PACK / "migrate-kotlin-feature/assets/test-foundations-spec.example.json"
        run(PACK / "migrate-kotlin-feature/scripts/scaffold_test_foundations.py", "--root", str(root), "--spec", str(spec), "--apply")
        self.assertTrue((root / "test/build.gradle.kts").is_file())
        self.assertTrue((root / "test/core/build.gradle.kts").is_file())
        self.assertTrue((root / "test/src/commonMain/kotlin/com/example/test").is_dir())

    def test_move_manifest_requires_reviewed_hash_and_writes_receipt(self) -> None:
        root = self.temporary / "repo"
        source = root / "app/src/main/kotlin/com/example/legacy/Order.kt"
        write(source, "package com.example.legacy\nclass Order\n")
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        manifest = {
            "schema_version": 1,
            "batch_id": "orders-domain-01",
            "feature": "orders",
            "layer": "domain",
            "moves": [{
                "from": source.relative_to(root).as_posix(),
                "to": "feature/orders/domain/src/main/kotlin/com/example/orders/Order.kt",
                "package_from": "com.example.legacy",
                "package_to": "com.example.orders",
                "expected_sha256": digest,
            }],
        }
        manifest_path = self.temporary / "moves.json"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        run(
            PACK / "migrate-kotlin-feature/scripts/apply_move_manifest.py",
            "--root", str(root), "--manifest", str(manifest_path), "--require-hashes",
            "--receipt-out", ".modularization/receipts/orders-domain-01.json", "--apply",
        )
        target = root / manifest["moves"][0]["to"]
        self.assertIn("package com.example.orders", target.read_text())
        receipt = json.loads((root / ".modularization/receipts/orders-domain-01.json").read_text())
        self.assertEqual(digest, receipt["moves"][0]["source_sha256"])

    def test_tracker_enforces_dependency_order_and_one_active_chunk(self) -> None:
        root = self.temporary / "repo"
        root.mkdir()
        subprocess.run(["git", "init", "-q", str(root)], check=True, timeout=20)
        plan = {
            "schema_version": 1,
            "audit_source": "fixture",
            "features": [{
                "name": "orders",
                "target_modules": [":feature:orders", ":feature:orders:domain", ":feature:orders:ui"],
                "existing_modules": [":feature:orders:domain"],
            }],
        }
        plan_path = self.temporary / "plan.json"
        plan_path.write_text(json.dumps(plan), encoding="utf-8")
        tracker = PACK / "modularize-kotlin-codebase/scripts/track_modularization.py"
        run(tracker, "--root", str(root), "init", "--plan", str(plan_path))
        run(tracker, "--root", str(root), "start", "--chunk", "conventions", expected=2)
        run(tracker, "--root", str(root), "start", "--chunk", "baseline")
        run(tracker, "--root", str(root), "complete", "--chunk", "baseline", "--note", "Baseline recorded.", "--no-check-reason", "Fixture has no Gradle wrapper.")
        run(tracker, "--root", str(root), "start", "--chunk", "conventions")
        run(tracker, "--root", str(root), "record-check", "--chunk", "conventions", "--argv-json", '["./gradlew","build"]', "--exit-code", "0", "--summary", "Build logic passed.")
        run(tracker, "--root", str(root), "complete", "--chunk", "conventions", "--note", "Convention proof complete.")
        state = json.loads((root / ".modularization/work-state.json").read_text())
        self.assertEqual("completed", next(item for item in state["chunks"] if item["id"] == "conventions")["status"])
        chunk_ids = {item["id"] for item in state["chunks"]}
        self.assertNotIn("test-foundations", chunk_ids)
        self.assertNotIn("foundations", chunk_ids)
        self.assertIn("feature-orders-domain", chunk_ids)
        self.assertIn("feature-orders-ui", chunk_ids)
        self.assertNotIn("feature-orders-data", chunk_ids)
        self.assertNotIn("feature-orders-navigation", chunk_ids)
        self.assertNotIn("feature-orders-test", chunk_ids)
        domain_chunk = next(item for item in state["chunks"] if item["id"] == "feature-orders-domain")
        self.assertIn("Validate the existing domain module", domain_chunk["title"])
        self.assertTrue((root / ".modularization/worklog.md").is_file())

    def test_tracker_requires_every_planned_check_result(self) -> None:
        root = self.temporary / "repo"
        root.mkdir()
        subprocess.run(["git", "init", "-q", str(root)], check=True, timeout=20)
        config = {
            "schema_version": 1,
            "project": {"name": "fixture"},
            "verification": {"baseline_commands": ["./gradlew check"]},
        }
        config_path = self.temporary / "config.json"
        config_path.write_text(json.dumps(config), encoding="utf-8")
        plan = {"schema_version": 1, "testing": {"shared_foundation_modules": [":test"]}, "features": []}
        plan_path = self.temporary / "plan.json"
        plan_path.write_text(json.dumps(plan), encoding="utf-8")
        tracker = PACK / "modularize-kotlin-codebase/scripts/track_modularization.py"
        run(tracker, "--root", str(root), "init", "--config", str(config_path), "--plan", str(plan_path))
        initial = json.loads((root / ".modularization/work-state.json").read_text())
        self.assertIn("test-foundations", {item["id"] for item in initial["chunks"]})
        run(tracker, "--root", str(root), "start", "--chunk", "baseline")
        run(
            tracker, "--root", str(root), "complete", "--chunk", "baseline",
            "--note", "Attempted without the planned command.", "--no-check-reason", "Not available.",
            expected=2,
        )
        run(
            tracker, "--root", str(root), "record-check", "--chunk", "baseline",
            "--argv-json", '["./gradlew","check"]', "--exit-code", "0", "--summary", "Baseline passed.",
        )
        run(tracker, "--root", str(root), "complete", "--chunk", "baseline", "--note", "Baseline recorded.")

    def test_tracker_orders_provider_shared_ui_before_consumer_ui(self) -> None:
        root = self.temporary / "repo"
        root.mkdir()
        subprocess.run(["git", "init", "-q", str(root)], check=True, timeout=20)
        plan = {
            "schema_version": 1,
            "features": [
                {
                    "name": "beta",
                    "target_modules": [":feature:beta", ":feature:beta:ui"],
                    "existing_modules": [],
                },
                {
                    "name": "alpha",
                    "target_modules": [
                        ":feature:alpha",
                        ":feature:alpha:shared-ui",
                        ":feature:alpha:ui",
                    ],
                    "existing_modules": [],
                },
            ],
            "plan_acceptance": {"shared_ui_graph": "pass"},
            "shared_ui_violations": [],
            "shared_ui_dependencies": [{
                "consumer": ":feature:beta:ui",
                "provider": ":feature:alpha:shared-ui",
                "source": "approved override",
            }],
        }
        plan_path = self.temporary / "shared-ui-order-plan.json"
        plan_path.write_text(json.dumps(plan), encoding="utf-8")
        tracker = PACK / "modularize-kotlin-codebase/scripts/track_modularization.py"

        missing_gate = json.loads(json.dumps(plan))
        missing_gate.pop("plan_acceptance")
        missing_gate.pop("shared_ui_violations")
        missing_gate_path = self.temporary / "missing-shared-ui-gate-plan.json"
        missing_gate_path.write_text(json.dumps(missing_gate), encoding="utf-8")
        rejected = run(
            tracker, "--root", str(root), "init", "--plan", str(missing_gate_path),
            expected=2,
        )
        self.assertIn("graph gate is unset", rejected.stderr)

        run(tracker, "--root", str(root), "init", "--plan", str(plan_path))
        state = json.loads((root / ".modularization/work-state.json").read_text())
        chunks = {item["id"]: item for item in state["chunks"]}
        self.assertIn("feature-alpha-shared-ui", chunks)
        self.assertIn(
            "feature-alpha-shared-ui",
            chunks["feature-beta-ui"]["depends_on"],
        )

    def test_tracker_rejects_failed_shared_ui_plan_gate(self) -> None:
        root = self.temporary / "repo"
        root.mkdir()
        subprocess.run(["git", "init", "-q", str(root)], check=True, timeout=20)
        plan = {
            "schema_version": 1,
            "features": [],
            "plan_acceptance": {"shared_ui_graph": "fail"},
            "shared_ui_violations": [{
                "source": ":feature:alpha:shared-ui",
                "target": ":feature:beta:shared-ui",
                "rule": "shared-ui-to-shared-ui",
                "evidence": "Shared UI must not depend on shared UI.",
            }],
        }
        plan_path = self.temporary / "failed-shared-ui-plan.json"
        plan_path.write_text(json.dumps(plan), encoding="utf-8")
        rejected = run(
            PACK / "modularize-kotlin-codebase/scripts/track_modularization.py",
            "--root", str(root), "init", "--plan", str(plan_path),
            expected=2,
        )
        self.assertIn("plan cannot initialize", rejected.stderr)

        legacy_chain = {
            "schema_version": 1,
            "features": [
                {
                    "name": "alpha",
                    "target_modules": [
                        ":feature:alpha",
                        ":feature:alpha:shared-ui",
                    ],
                    "existing_modules": [],
                },
                {
                    "name": "beta",
                    "target_modules": [
                        ":feature:beta",
                        ":feature:beta:shared-ui",
                    ],
                    "existing_modules": [],
                },
            ],
            "plan_acceptance": {"shared_ui_graph": "pass"},
            "shared_ui_violations": [],
            "shared_ui_dependencies": [{
                "consumer": ":feature:alpha:shared-ui",
                "provider": ":feature:beta:shared-ui",
            }],
        }
        legacy_path = self.temporary / "legacy-shared-ui-chain-plan.json"
        legacy_path.write_text(json.dumps(legacy_chain), encoding="utf-8")
        rejected = run(
            PACK / "modularize-kotlin-codebase/scripts/track_modularization.py",
            "--root", str(root), "init", "--plan", str(legacy_path),
            expected=2,
        )
        self.assertIn("consumer feature ui", rejected.stderr)

    def test_architecture_checker_enforces_conventions_and_test_module(self) -> None:
        root = self.temporary / "repo"
        write(root / "settings.gradle.kts", 'pluginManagement { includeBuild("build-logic") }\ninclude(":feature:orders", ":feature:orders:domain", ":test")\n')
        write(root / "feature/orders/build.gradle.kts", 'plugins { id("example.feature.root") }\ndependencies { implementation(project(":feature:orders:domain")) }\n')
        write(root / "feature/orders/domain/build.gradle.kts", 'plugins { id("example.feature.domain") }\n')
        write(root / "test/build.gradle.kts", 'plugins { id("example.test.support") }\n')
        write(root / "build-logic/settings.gradle.kts", 'rootProject.name = "build-logic"\n')
        write(root / ".modularization/synthetic/build.gradle.kts", 'dependencies { implementation(project(":feature:orders:domain")) }\n')
        rules = json.loads((PACK / "verify-kotlin-modules/assets/architecture-rules.example.json").read_text())
        rules["required_feature_layers"] = ["domain"]
        rules["required_feature_layers_by_feature"] = {"orders": ["domain"]}
        rules["required_test_modules"] = [":test"]
        rules["conventions"]["validate_included_build_plugins"] = False
        rules["conventions"]["required_registered_plugin_ids"] = []
        rules["conventions"]["required_plugins_by_role"] = {
            "domain": {"any_of": ["example.feature.domain"], "all_of": []},
            "test-support": {"any_of": ["example.test.support"], "all_of": []},
        }
        rules_path = self.temporary / "rules.json"
        rules_path.write_text(json.dumps(rules), encoding="utf-8")
        result = run(PACK / "verify-kotlin-modules/scripts/check_architecture.py", "--root", str(root), "--rules", str(rules_path))
        self.assertIn("0 error(s)", result.stdout)

    def test_checker_validates_per_feature_shapes_and_convention_implementations(self) -> None:
        root = self.temporary / "repo"
        write(root / "settings.gradle.kts", 'pluginManagement { includeBuild("build-logic") }\ninclude(":feature:orders", ":feature:orders:domain", ":feature:profile", ":feature:profile:ui")\n')
        write(root / "feature/orders/build.gradle.kts")
        write(root / "feature/orders/domain/build.gradle.kts")
        write(root / "feature/profile/build.gradle.kts")
        write(root / "feature/profile/ui/build.gradle.kts")
        write(root / "build-logic/settings.gradle.kts", 'rootProject.name = "build-logic"\n')
        write(
            root / "build-logic/convention/build.gradle.kts",
            'plugins { `kotlin-dsl` }\n'
            'gradlePlugin { plugins { register("domain") { id = "example.feature.domain"; implementationClass = "com.example.DomainPlugin" } } }\n',
        )
        rules = json.loads((PACK / "verify-kotlin-modules/assets/architecture-rules.example.json").read_text())
        rules["required_feature_layers"] = []
        rules["required_feature_layers_by_feature"] = {"orders": ["domain", "data"], "profile": ["ui"]}
        rules["check_settings_registration"] = False
        rules["required_test_modules"] = []
        rules["conventions"]["included_builds"] = ["build-logic"]
        rules["conventions"]["required_registered_plugin_ids"] = ["example.feature.domain", "example.feature.ui"]
        rules["conventions"]["required_plugins_by_role"] = {}
        rules_path = self.temporary / "rules.json"
        findings_path = self.temporary / "findings.json"
        rules_path.write_text(json.dumps(rules), encoding="utf-8")
        run(
            PACK / "verify-kotlin-modules/scripts/check_architecture.py",
            "--root", str(root), "--rules", str(rules_path), "--json-out", str(findings_path),
            expected=1,
        )
        finding_ids = {item["rule"] for item in json.loads(findings_path.read_text())["findings"]}
        self.assertIn("missing-feature-layer", finding_ids)
        self.assertIn("convention-settings-registration", finding_ids)
        self.assertIn("missing-convention-implementation", finding_ids)
        self.assertIn("missing-convention-plugin-registration", finding_ids)

    def test_generated_convention_pack_is_structurally_enforceable(self) -> None:
        root = self.temporary / "repo"
        write(
            root / "settings.gradle.kts",
            'pluginManagement { includeBuild("build-logic") }\n'
            'include(":feature:orders", ":feature:orders:domain", ":feature:orders:data", '
            '":feature:orders:navigation", ":feature:orders:ui", ":feature:orders:test")\n',
        )
        write(root / "feature/orders/build.gradle.kts")
        role_plugins = {
            "domain": "com.example.convention.feature.domain",
            "data": "com.example.convention.feature.data",
            "navigation": "com.example.convention.feature.navigation",
            "ui": "com.example.convention.feature.ui",
            "test": "com.example.convention.test.support",
        }
        for role, plugin in role_plugins.items():
            write(root / f"feature/orders/{role}/build.gradle.kts", f'plugins {{ id("{plugin}") }}\n')
        run(
            PACK / "design-gradle-conventions/scripts/scaffold_build_logic.py",
            "--root", str(root),
            "--spec", str(PACK / "design-gradle-conventions/assets/build-logic-spec.example.json"),
            "--apply",
        )
        rules_path = self.temporary / "rules.json"
        rules_path.write_text((PACK / "verify-kotlin-modules/assets/architecture-rules.example.json").read_text(), encoding="utf-8")
        result = run(
            PACK / "verify-kotlin-modules/scripts/check_architecture.py",
            "--root", str(root), "--rules", str(rules_path),
        )
        self.assertIn("0 error(s)", result.stdout)

    def test_checker_allows_ui_consumers_and_rejects_shared_ui_chains(self) -> None:
        root = self.temporary / "repo"
        write(root / "core/ui/build.gradle.kts")
        write(root / "feature/alpha/build.gradle.kts")
        write(root / "feature/alpha/domain/build.gradle.kts")
        write(root / "feature/alpha/navigation/build.gradle.kts")
        write(
            root / "feature/alpha/shared-ui/build.gradle.kts",
            'dependencies {\n'
            '  implementation(project(":core:ui"))\n'
            '  implementation(project(":feature:alpha:domain"))\n'
            '  implementation(project(":feature:alpha:navigation"))\n'
            '}\n',
        )
        write(
            root / "feature/alpha/ui/build.gradle.kts",
            'dependencies { implementation(project(":feature:alpha:shared-ui")) }\n',
        )
        write(root / "feature/beta/build.gradle.kts")
        write(root / "feature/beta/domain/build.gradle.kts")
        write(
            root / "feature/beta/shared-ui/build.gradle.kts",
            'dependencies { implementation(project(":core:ui")) }\n',
        )
        write(
            root / "feature/beta/ui/build.gradle.kts",
            'dependencies { implementation(project(":feature:alpha:shared-ui")) }\n',
        )
        write(
            root / "core/ui/src/main/kotlin/com/example/core/ui/CoreWidget.kt",
            "package com.example.core.ui\nclass CoreWidget\n",
        )
        write(
            root / "feature/alpha/domain/src/main/kotlin/com/example/alpha/domain/Alpha.kt",
            "package com.example.alpha.domain\nclass Alpha\n",
        )
        write(
            root / "feature/alpha/navigation/src/main/kotlin/com/example/alpha/navigation/AlphaRoute.kt",
            "package com.example.alpha.navigation\nclass AlphaRoute\n",
        )
        write(
            root / "feature/alpha/shared-ui/src/main/kotlin/com/example/alpha/sharedui/AlphaCard.kt",
            "package com.example.alpha.sharedui\n"
            "import com.example.core.ui.CoreWidget\n"
            "class AlphaCard(val core: CoreWidget)\n",
        )
        write(
            root / "feature/alpha/ui/src/main/kotlin/com/example/alpha/ui/AlphaScreen.kt",
            "package com.example.alpha.ui\n"
            "import com.example.alpha.sharedui.AlphaCard\n"
            "class AlphaScreen(val card: AlphaCard)\n",
        )
        write(
            root / "feature/beta/shared-ui/src/main/kotlin/com/example/beta/sharedui/BetaCard.kt",
            "package com.example.beta.sharedui\nclass BetaCard\n",
        )
        beta_screen = root / "feature/beta/ui/src/main/kotlin/com/example/beta/ui/BetaScreen.kt"
        write(
            beta_screen,
            "package com.example.beta.ui\n"
            "import com.example.alpha.sharedui.AlphaCard\n"
            "class BetaScreen(val card: AlphaCard)\n",
        )
        rules = json.loads(
            (PACK / "verify-kotlin-modules/assets/architecture-rules.example.json").read_text()
        )
        rules["required_feature_layers"] = []
        rules["required_feature_layers_by_feature"] = {}
        rules["check_settings_registration"] = False
        rules["conventions"] = {
            "included_builds": [],
            "validate_included_build_plugins": False,
            "required_registered_plugin_ids": [],
            "required_plugins_by_role": {},
            "forbidden_plugins_by_role": {},
        }
        rules_path = self.temporary / "shared-ui-rules.json"
        rules_path.write_text(json.dumps(rules), encoding="utf-8")
        checker = PACK / "verify-kotlin-modules/scripts/check_architecture.py"
        valid = run(checker, "--root", str(root), "--rules", str(rules_path))
        self.assertIn("0 error(s)", valid.stdout)

        write(
            root / "feature/alpha/shared-ui/build.gradle.kts",
            'dependencies {\n'
            '  implementation(project(":feature:beta:shared-ui"))\n'
            '  implementation(project(":feature:beta:domain"))\n'
            '  implementation(project(":feature:beta:ui"))\n'
            '  implementation(project(":feature:beta"))\n'
            '}\n',
        )
        write(
            root / "feature/alpha/shared-ui/src/main/kotlin/com/example/alpha/sharedui/AlphaCard.kt",
            "package com.example.alpha.sharedui\n"
            "import com.example.beta.sharedui.BetaCard\n"
            "import com.example.beta.ui.BetaScreen\n"
            "class AlphaCard(val beta: BetaCard, val screen: BetaScreen)\n",
        )
        write(
            root / "feature/beta/domain/build.gradle.kts",
            'dependencies { implementation(project(path = ":feature:alpha:shared-ui")) }\n',
        )
        write(
            root / "feature/beta/ui/build.gradle.kts",
            'dependencies {\n'
            '  implementation(project(":feature:alpha:shared-ui"))\n'
            '  implementation(project(":feature:alpha:ui"))\n'
            '}\n',
        )
        write(
            root / "core/ui/build.gradle.kts",
            'dependencies { implementation(project(":feature:alpha:shared-ui")) }\n',
        )
        write(
            root / "app/build.gradle.kts",
            "dependencies { implementation(projects.feature.alpha.sharedUi) }\n",
        )
        findings_path = self.temporary / "invalid-shared-ui-findings.json"
        run(
            checker, "--root", str(root), "--rules", str(rules_path),
            "--json-out", str(findings_path), expected=1,
        )
        findings = json.loads(findings_path.read_text())["findings"]
        finding_ids = {item["rule"] for item in findings}
        self.assertIn("shared-ui-to-shared-ui", finding_ids)
        self.assertIn("shared-ui-to-foreign-feature-contract", finding_ids)
        self.assertIn("shared-ui-to-feature-ui", finding_ids)
        self.assertIn("shared-ui-to-feature-root", finding_ids)
        self.assertIn("lower-layer-to-shared-ui", finding_ids)
        self.assertIn("invalid-shared-ui-consumer", finding_ids)
        self.assertIn("cross-feature-dependency", finding_ids)
        self.assertTrue(any(
            item["rule"] == "invalid-shared-ui-consumer"
            and item["source"] == ":app"
            and item["target"] == ":feature:alpha:shared-ui"
            for item in findings
        ))

        non_waivable = json.loads(json.dumps(rules))
        non_waivable["exceptions"] = [{
            "rule": "shared-ui-to-shared-ui",
            "source": ":feature:alpha:shared-ui",
            "target": ":feature:beta:shared-ui",
            "reason": "Temporary migration shortcut.",
            "owner": "mobile",
            "remove_when": "Migration completes",
        }]
        non_waivable_path = self.temporary / "non-waivable-shared-ui-rules.json"
        non_waivable_path.write_text(json.dumps(non_waivable), encoding="utf-8")
        rejected = run(
            checker, "--root", str(root), "--rules", str(non_waivable_path),
            expected=2,
        )
        self.assertIn("shared-ui hard rule cannot be suppressed", rejected.stderr)

    def test_checker_applies_shared_ui_boundaries_to_legacy_v1_rules(self) -> None:
        root = self.temporary / "repo"
        write(root / "feature/alpha/build.gradle.kts")
        write(
            root / "feature/alpha/domain/build.gradle.kts",
            'dependencies { implementation(project(":feature:alpha:shared-ui")) }\n',
        )
        write(root / "feature/alpha/data/build.gradle.kts")
        write(
            root / "feature/alpha/shared-ui/build.gradle.kts",
            'dependencies { implementation(project(":feature:alpha:data")) }\n',
        )
        write(
            root / "feature/beta/build.gradle.kts",
            'dependencies { implementation(project(":feature:alpha:shared-ui")) }\n',
        )
        write(
            root / "feature/beta/ui/build.gradle.kts",
            'dependencies { implementation(project(":feature:alpha:shared-ui")) }\n',
        )
        legacy_rules = {
            "schema_version": 1,
            "feature_root": "feature",
            "required_feature_layers": [],
            "required_feature_layers_by_feature": {},
            "check_settings_registration": False,
            "test_support_names": ["test", "test-support", "fixtures"],
            "module_roles": {
                "*/domain": "domain",
                "*/data": "data",
                "*/navigation": "navigation",
                "*/ui": "ui",
                "*/test": "test-support",
            },
            "forbidden_target_roles": {
                "domain": ["data", "navigation", "ui", "app", "test-support"],
                "data": ["navigation", "ui", "app", "test-support"],
                "navigation": ["data", "ui", "app", "test-support"],
                "ui": ["data", "app", "test-support"],
                "aggregation": ["test-support"],
            },
            "cross_feature": {
                "severity": "error",
                "allowed_target_roles": ["domain", "navigation"],
            },
            "conventions": {
                "included_builds": [],
                "validate_included_build_plugins": False,
                "required_registered_plugin_ids": [],
                "required_plugins_by_role": {},
                "forbidden_plugins_by_role": {},
            },
            "ignored_paths": [],
            "ignored_import_prefixes": [],
            "exceptions": [],
        }
        rules_path = self.temporary / "legacy-v1-rules.json"
        rules_path.write_text(json.dumps(legacy_rules), encoding="utf-8")
        findings_path = self.temporary / "legacy-v1-findings.json"
        run(
            PACK / "verify-kotlin-modules/scripts/check_architecture.py",
            "--root", str(root), "--rules", str(rules_path),
            "--json-out", str(findings_path), expected=1,
        )
        finding_ids = {
            item["rule"] for item in json.loads(findings_path.read_text())["findings"]
        }
        self.assertIn("lower-layer-to-shared-ui", finding_ids)
        self.assertIn("shared-ui-to-forbidden-layer", finding_ids)
        self.assertIn("feature-root-to-foreign-shared-ui", finding_ids)
        self.assertNotIn("cross-feature-dependency", finding_ids)

    def test_type_safe_accessor_normalizes_hyphenated_shared_ui_path(self) -> None:
        root = self.temporary / "repo"
        write(root / "modules/feature/care-plan/shared-ui/build.gradle.kts")
        write(
            root / "app/build.gradle.kts",
            "dependencies {\n"
            "  implementation(projects.modules.feature.carePlan.sharedUi)\n"
            "}\n",
        )

        audit_path = self.temporary / "hyphenated-accessor-audit.json"
        run(
            PACK / "audit-kotlin-architecture/scripts/audit_codebase.py",
            "--root", str(root), "--root-package", "com.example",
            "--json-out", str(audit_path),
        )
        overrides_path = self.temporary / "hyphenated-accessor-overrides.json"
        overrides_path.write_text(
            json.dumps({
                "schema_version": 1,
                "feature_root": "modules/feature",
            }),
            encoding="utf-8",
        )
        plan_path = self.temporary / "hyphenated-accessor-plan.json"
        run(
            PACK / "audit-kotlin-architecture/scripts/plan_modules.py",
            "--audit", str(audit_path), "--overrides", str(overrides_path),
            "--json-out", str(plan_path),
        )
        plan = json.loads(plan_path.read_text())
        self.assertTrue(any(
            item["source"] == ":app"
            and item["target"] == ":modules:feature:care-plan:shared-ui"
            and item["rule"] == "invalid-shared-ui-consumer"
            for item in plan["shared_ui_violations"]
        ))

        convention_path = self.temporary / "hyphenated-accessor-conventions.json"
        run(
            PACK / "design-gradle-conventions/scripts/analyze_gradle_conventions.py",
            "--root", str(root), "--json-out", str(convention_path),
        )
        app_module = next(
            item for item in json.loads(convention_path.read_text())["modules"]
            if item["path"] == ":app"
        )
        self.assertIn(
            {
                "configuration": "implementation",
                "dependency": "project(:modules:feature:care-plan:shared-ui)",
            },
            app_module["dependencies"],
        )

        rules = json.loads(
            (PACK / "verify-kotlin-modules/assets/architecture-rules.example.json").read_text()
        )
        rules["feature_root"] = "modules/feature"
        rules["required_feature_layers"] = []
        rules["required_feature_layers_by_feature"] = {}
        rules["check_settings_registration"] = False
        rules["conventions"] = {
            "included_builds": [],
            "validate_included_build_plugins": False,
            "required_registered_plugin_ids": [],
            "required_plugins_by_role": {},
            "forbidden_plugins_by_role": {},
        }
        rules_path = self.temporary / "hyphenated-accessor-rules.json"
        rules_path.write_text(json.dumps(rules), encoding="utf-8")
        findings_path = self.temporary / "hyphenated-accessor-findings.json"
        run(
            PACK / "verify-kotlin-modules/scripts/check_architecture.py",
            "--root", str(root), "--rules", str(rules_path),
            "--json-out", str(findings_path), expected=1,
        )
        findings = json.loads(findings_path.read_text())["findings"]
        self.assertTrue(any(
            item["source"] == ":app"
            and item["target"] == ":modules:feature:care-plan:shared-ui"
            and item["rule"] == "invalid-shared-ui-consumer"
            for item in findings
        ))

    def test_type_safe_accessor_normalizes_underscore_shared_ui_path(self) -> None:
        root = self.temporary / "underscore-repo"
        write(root / "feature/care_plan/shared-ui/build.gradle.kts")
        write(root / "feature/consumer/ui/build.gradle.kts", (
            "dependencies {\n"
            "  implementation(projects.feature.carePlan.sharedUi)\n"
            "  implementation(libs.projects.feature.other.sharedUi)\n"
            "  // implementation(projects.feature.other.sharedUi)\n"
            "  /* implementation(project(\":feature:other:ui\")) */\n"
            "}\n"
        ))

        audit_path = self.temporary / "underscore-accessor-audit.json"
        run(
            PACK / "audit-kotlin-architecture/scripts/audit_codebase.py",
            "--root", str(root), "--root-package", "com.example",
            "--json-out", str(audit_path),
        )
        audit = json.loads(audit_path.read_text())
        consumer = next(
            module for module in audit["modules"]
            if module["path"] == ":feature:consumer:ui"
        )
        self.assertEqual(
            [":feature:care_plan:shared-ui"],
            consumer["project_dependencies"],
        )

        convention_path = self.temporary / "underscore-accessor-conventions.json"
        run(
            PACK / "design-gradle-conventions/scripts/analyze_gradle_conventions.py",
            "--root", str(root), "--json-out", str(convention_path),
        )
        consumer_conventions = next(
            module for module in json.loads(convention_path.read_text())["modules"]
            if module["path"] == ":feature:consumer:ui"
        )
        self.assertIn(
            {
                "configuration": "implementation",
                "dependency": "project(:feature:care_plan:shared-ui)",
            },
            consumer_conventions["dependencies"],
        )

        rules = json.loads(
            (PACK / "verify-kotlin-modules/assets/architecture-rules.example.json").read_text()
        )
        rules["required_feature_layers"] = []
        rules["required_feature_layers_by_feature"] = {}
        rules["check_settings_registration"] = False
        rules["conventions"] = {
            "included_builds": [],
            "validate_included_build_plugins": False,
            "required_registered_plugin_ids": [],
            "required_plugins_by_role": {},
            "forbidden_plugins_by_role": {},
        }
        rules_path = self.temporary / "underscore-accessor-rules.json"
        rules_path.write_text(json.dumps(rules), encoding="utf-8")
        run(
            PACK / "verify-kotlin-modules/scripts/check_architecture.py",
            "--root", str(root), "--rules", str(rules_path),
        )

        spec = json.loads(
            (PACK / "migrate-kotlin-feature/assets/feature-spec-with-shared-ui.example.json").read_text()
        )
        spec["feature"] = "care_plan"
        spec["package"] = "com.example.careplan"
        spec["layers"]["shared-ui"]["dependencies"].append(
            "implementation(libs.projects.feature.other.sharedUi)"
        )
        owner_dependencies = {
            "domain": "projects.feature.carePlan.domain",
            "navigation": "projects.feature.carePlan.navigation",
            "shared-ui": "projects.feature.carePlan.sharedUi",
            "ui": "projects.feature.carePlan.ui",
        }
        for config in list(spec["layers"].values()) + [spec["aggregation"]]:
            config["dependencies"] = [
                re.sub(
                    r'project\(":feature:orders:(domain|navigation|shared-ui|ui)"\)',
                    lambda match: owner_dependencies[match.group(1)],
                    dependency,
                )
                for dependency in config.get("dependencies", [])
            ]
            config["test_dependencies"] = [
                dependency.replace(":feature:orders:test", ":feature:care_plan:test")
                for dependency in config.get("test_dependencies", [])
            ]
        spec_path = self.temporary / "underscore-owner-spec.json"
        spec_path.write_text(json.dumps(spec), encoding="utf-8")
        run(
            PACK / "migrate-kotlin-feature/scripts/scaffold_feature.py",
            "--root", str(root), "--spec", str(spec_path),
        )

    def test_gradle_check_suggestions_use_valid_root_task_and_feature_descendants(self) -> None:
        root = self.temporary / "repo"
        write(root / "settings.gradle.kts", 'include(":feature:orders", ":feature:orders:domain", ":feature:orders:shared-ui", ":feature:orders:ui")\n')
        write(root / "build.gradle.kts", 'plugins { id("com.android.application") apply false }\n')
        write(root / "feature/orders/build.gradle.kts")
        write(root / "feature/orders/domain/build.gradle.kts", 'plugins { id("example.feature.domain") }\n')
        write(root / "feature/orders/shared-ui/build.gradle.kts", 'plugins { id("example.feature.ui") }\n')
        write(root / "feature/orders/ui/build.gradle.kts", 'plugins { id("example.feature.ui") }\n')
        write(root / ".modularization/synthetic/build.gradle.kts", 'plugins { id("com.android.application") }\n')
        result = run(
            PACK / "verify-kotlin-modules/scripts/suggest_gradle_checks.py",
            "--root", str(root), "--changed", "feature/orders", "--platform-rule", ":feature:orders:*=android",
        )
        self.assertNotIn("::check", result.stdout)
        self.assertNotIn(":assembleDebug", result.stdout)
        self.assertNotIn(".modularization", result.stdout)
        self.assertIn("./gradlew :feature:orders:check", result.stdout)
        self.assertIn("./gradlew :feature:orders:domain:check", result.stdout)
        self.assertIn("./gradlew :feature:orders:shared-ui:check", result.stdout)
        self.assertIn("./gradlew :feature:orders:ui:check", result.stdout)
        self.assertIn("./gradlew :feature:orders:domain:testDebugUnitTest", result.stdout)
        dependents = result.stdout.split("## 3. Direct dependents", 1)[1].split("## 4.", 1)[0]
        self.assertNotIn(":feature:orders:domain:check", dependents)


if __name__ == "__main__":
    unittest.main()
