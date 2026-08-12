"""Fixture-driven tests for focused modularization boundary skills."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

from helpers import PACK, PackTestCase, load_json, run, skill_script, write


def module_dir(root: Path, module: str) -> Path:
    return root.joinpath(*[part for part in module.split(":") if part])


def write_module(root: Path, module: str, dependencies: list[str] | None = None, *, groovy: bool = False) -> None:
    dependencies = dependencies or []
    directory = module_dir(root, module)
    suffix = "build.gradle" if groovy else "build.gradle.kts"
    if groovy:
        lines = ["plugins { id 'org.jetbrains.kotlin.multiplatform' }", "dependencies {"]
        lines += [f"  implementation(project(path: '{dependency}'))" for dependency in dependencies]
        lines.append("}")
    else:
        lines = ["plugins { kotlin(\"multiplatform\") }", "kotlin { sourceSets { commonMain.dependencies {"]
        lines += [f'  implementation(project("{dependency}"))' for dependency in dependencies]
        lines += ["} } }"]
    write(directory / suffix, "\n".join(lines) + "\n")


def write_settings(root: Path, modules: list[str]) -> None:
    write(root / "settings.gradle.kts", "rootProject.name = \"fixture\"\n" + "include(" + ", ".join(json.dumps(item) for item in modules) + ")\n")


def write_json(path: Path, payload: dict) -> Path:
    write(path, json.dumps(payload, indent=2) + "\n")
    return path


def assert_valid_artifact(case: PackTestCase, payload: dict, kind: str) -> None:
    if str(PACK) not in sys.path:
        sys.path.insert(0, str(PACK))
    from common.artifact_schema import validate_artifact

    case.assertEqual([], validate_artifact(payload, kind))


class FocusedArtifactSchemaTests(PackTestCase):
    def test_new_artifact_kinds_are_registered(self) -> None:
        sys.path.insert(0, str(PACK))
        from common.artifact_schema import ARTIFACT_KINDS

        expected = {
            "feature-integration-audit", "feature-integration-plan",
            "di-boundary-audit", "di-migration-plan",
            "feature-coupling-report", "feature-decoupling-plan",
            "data-boundary-audit", "data-boundary-plan",
            "test-boundary-audit", "test-migration-plan",
            "resource-audit", "resource-migration-plan",
            "persistence-boundary-audit", "persistence-migration-plan",
            "module-consolidation-audit", "module-consolidation-plan",
            "module-consolidation-check",
        }
        self.assertTrue(expected.issubset(ARTIFACT_KINDS))


class IntegrateFeatureTests(PackTestCase):
    def test_audit_plan_check_and_determinism(self) -> None:
        root = self.temporary / "repo"
        modules = [":feature:orders", ":feature:orders:domain", ":feature:orders:data", ":feature:orders:navigation", ":feature:orders:ui", ":composeApp"]
        for module in modules:
            write_module(root, module, [":feature:orders"] if module == ":composeApp" else [])
        write_settings(root, modules)
        write(
            root / "feature/orders/data/src/commonMain/kotlin/com/example/orders/data/OrdersModule.kt",
            "package com.example.orders.data\nimport dev.zacsweers.metro.ContributesBinding\n@ContributesBinding class OrdersModule\n",
        )
        write(
            root / "feature/orders/navigation/src/commonMain/kotlin/com/example/orders/navigation/OrdersDestination.kt",
            "package com.example.orders.navigation\ninterface Destination\nobject OrdersDestination : Destination\nfun ordersNavGraph() = Unit\n",
        )
        write(
            root / "composeApp/src/commonMain/kotlin/com/example/app/App.kt",
            "package com.example.app\nimport dev.zacsweers.metro.ContributesTo\n@ContributesTo(AppScope::class) object OrdersFeatureModule\nfun app() { ordersNavGraph(); OrdersDestination.serializer() }\n",
        )
        rules = write_json(self.temporary / "rules.json", {
            "schema_version": 1,
            "required_layers": ["domain", "data", "navigation", "ui"],
            "app_modules": [":composeApp"],
            "require_app_dependency": True,
            "require_di": True,
            "require_navigation": True,
            "require_serializer_registration": True,
            "app_entry_patterns": ["ordersNavGraph", "OrdersDestination.serializer()"],
        })
        script = skill_script("integrate-kotlin-feature", "integrate_feature.py")
        first = self.temporary / "first.json"
        second = self.temporary / "second.json"
        run(script, "audit", "--root", root, "--feature", "orders", "--rules", rules, "--json-out", first)
        run(script, "audit", "--root", root, "--feature", "orders", "--rules", rules, "--json-out", second)
        self.assertEqual(first.read_text(), second.read_text())
        payload = load_json(first)
        assert_valid_artifact(self, payload, "feature-integration-audit")
        self.assertTrue(all(value == "pass" for value in payload["gates"].values()), payload["gates"])
        plan = self.temporary / "plan.json"
        run(script, "plan", "--root", root, "--audit", first, "--rules", rules, "--json-out", plan)
        plan_payload = load_json(plan)
        assert_valid_artifact(self, plan_payload, "feature-integration-plan")
        self.assertEqual([], plan_payload["actions"])
        run(script, "check", "--root", root, "--feature", "orders", "--rules", rules)


class DependencyInjectionTests(PackTestCase):
    def test_detects_framework_and_layer_violation(self) -> None:
        root = self.temporary / "repo"
        modules = [":feature:orders:domain", ":composeApp"]
        for module in modules:
            write_module(root, module)
        write_settings(root, modules)
        write(
            root / "feature/orders/domain/src/commonMain/kotlin/com/example/orders/domain/UseCase.kt",
            "package com.example.orders.domain\nimport dev.zacsweers.metro.Inject\n@Inject class OrdersUseCase\n",
        )
        write(
            root / "composeApp/src/commonMain/kotlin/com/example/app/AppGraph.kt",
            "package com.example.app\nimport dev.zacsweers.metro.DependencyGraph\n@DependencyGraph(AppScope::class) interface AppGraph\n",
        )
        rules = write_json(self.temporary / "di.json", {
            "schema_version": 1,
            "approved_framework": "metro",
            "framework_free_layers": ["domain"],
            "required_graph_modules": [":composeApp"],
            "required_platform_source_sets": [],
        })
        script = skill_script("modularize-kotlin-dependency-injection", "analyze_di.py")
        audit = self.temporary / "audit.json"
        run(script, "audit", "--root", root, "--rules", rules, "--json-out", audit)
        payload = load_json(audit)
        assert_valid_artifact(self, payload, "di-boundary-audit")
        self.assertIn("metro", payload["frameworks"])
        self.assertTrue(any(item["rule"] == "framework-in-free-layer" for item in payload["findings"]))
        plan = self.temporary / "plan.json"
        run(script, "plan", "--root", root, "--audit", audit, "--rules", rules, "--json-out", plan)
        plan_payload = load_json(plan)
        assert_valid_artifact(self, plan_payload, "di-migration-plan")
        self.assertEqual("fail", plan_payload["gates"]["plan_ready"])


class FeatureDecouplingTests(PackTestCase):
    def test_groovy_edges_classified_and_allowance_applied(self) -> None:
        root = self.temporary / "repo"
        write_module(root, ":feature:care:ui", [":feature:orders:ui", ":feature:orders:data", ":feature:orders:navigation"], groovy=True)
        for module in (":feature:orders:ui", ":feature:orders:data", ":feature:orders:navigation"):
            write_module(root, module, groovy=True)
        rules = write_json(self.temporary / "coupling.json", {
            "schema_version": 1,
            "allowed_edges": [{"source": ":feature:care:ui", "target": ":feature:orders:navigation", "reason": "Intentional provider flow"}],
        })
        script = skill_script("decouple-kotlin-features", "analyze_feature_coupling.py")
        report = self.temporary / "report.json"
        run(script, "audit", "--root", root, "--rules", rules, "--json-out", report)
        payload = load_json(report)
        assert_valid_artifact(self, payload, "feature-coupling-report")
        self.assertEqual(3, len(payload["edges"]))
        self.assertEqual(2, len(payload["unresolved"]))
        self.assertTrue(any(item["allowed_reason"] for item in payload["edges"] if item["target"].endswith(":navigation")))
        plan = self.temporary / "plan.json"
        run(script, "plan", "--root", root, "--report", report, "--json-out", plan)
        plan_payload = load_json(plan)
        assert_valid_artifact(self, plan_payload, "feature-decoupling-plan")
        self.assertEqual("care", plan_payload["batches"][0]["feature"])


class DataBoundaryTests(PackTestCase):
    def test_wire_snapshot_and_domain_data_assignments(self) -> None:
        root = self.temporary / "repo"
        for module in (":legacy:domain", ":feature:orders:domain", ":feature:orders:data"):
            write_module(root, module)
        write(
            root / "legacy/domain/src/commonMain/kotlin/com/example/legacy/OrderRepository.kt",
            "package com.example.legacy\ninterface OrderRepository\n",
        )
        write(
            root / "legacy/domain/src/commonMain/kotlin/com/example/legacy/OrderResponse.kt",
            "package com.example.legacy\nimport kotlinx.serialization.SerialName\nimport kotlinx.serialization.Serializable\n@Serializable data class OrderResponse(@SerialName(\"order_id\") val id: String)\n",
        )
        rules = write_json(self.temporary / "data.json", {
            "schema_version": 1,
            "target_feature": "orders",
            "target_domain_module": ":feature:orders:domain",
            "target_data_module": ":feature:orders:data",
        })
        script = skill_script("migrate-kotlin-data-boundaries", "analyze_data_boundaries.py")
        audit = self.temporary / "audit.json"
        run(script, "audit", "--root", root, "--rules", rules, "--json-out", audit)
        payload = load_json(audit)
        assert_valid_artifact(self, payload, "data-boundary-audit")
        self.assertEqual(["order_id"], payload["wire_contracts"][0]["serial_names"])
        self.assertTrue(any(item["rule"] == "wire-dto-in-domain-review" for item in payload["findings"]))
        plan = self.temporary / "plan.json"
        run(script, "plan", "--root", root, "--audit", audit, "--rules", rules, "--json-out", plan)
        plan_payload = load_json(plan)
        assert_valid_artifact(self, plan_payload, "data-boundary-plan")
        targets = {item["target_module"] for item in plan_payload["assignments"]}
        self.assertEqual({":feature:orders:domain", ":feature:orders:data"}, targets)


class TestMigrationTests(PackTestCase):
    def test_source_set_match_hash_and_production_test_edge(self) -> None:
        root = self.temporary / "repo"
        write_module(root, ":feature:orders:domain", [":feature:orders:test"])
        write_module(root, ":feature:orders:test")
        write(
            root / "feature/orders/domain/src/commonMain/kotlin/com/example/orders/OrderPolicy.kt",
            "package com.example.orders\nclass OrderPolicy\n",
        )
        write(
            root / "feature/orders/domain/src/commonTest/kotlin/com/example/orders/OrderPolicyTest.kt",
            "package com.example.orders\nclass OrderPolicyTest\n",
        )
        rules = write_json(self.temporary / "tests.json", {
            "schema_version": 1,
            "source_set_map": {"commonMain": "commonTest"},
            "task_templates": {"commonTest": ["{module}:testAndroidHostTest"]},
            "test_support_modules": [":feature:orders:test"],
        })
        script = skill_script("migrate-kotlin-tests", "plan_test_migration.py")
        audit = self.temporary / "audit.json"
        run(script, "audit", "--root", root, "--rules", rules, "--json-out", audit)
        audit_payload = load_json(audit)
        assert_valid_artifact(self, audit_payload, "test-boundary-audit")
        self.assertEqual("fail", audit_payload["gates"]["production_test_edges"])
        plan = self.temporary / "plan.json"
        run(script, "plan", "--root", root, "--audit", audit, "--rules", rules, "--json-out", plan)
        plan_payload = load_json(plan)
        assert_valid_artifact(self, plan_payload, "test-migration-plan")
        move = plan_payload["moves"][0]
        self.assertEqual("commonTest", move["target_source_set"])
        self.assertEqual(64, len(move["expected_sha256"]))
        self.assertIn(":feature:orders:domain:testAndroidHostTest", plan_payload["verification"])


class ResourceMigrationTests(PackTestCase):
    def test_variants_consumers_and_hashes_preserved(self) -> None:
        root = self.temporary / "repo"
        write_module(root, ":legacy:ui")
        write_module(root, ":feature:orders:ui")
        write(root / "legacy/ui/src/commonMain/composeResources/values/strings.xml", '<resources><string name="orders_title">Orders</string></resources>\n')
        write(root / "legacy/ui/src/commonMain/composeResources/values-fr/strings.xml", '<resources><string name="orders_title">Commandes</string></resources>\n')
        write(
            root / "feature/orders/ui/src/commonMain/kotlin/com/example/orders/OrdersScreen.kt",
            "package com.example.orders\nfun screen() = Res.string.orders_title\n",
        )
        script = skill_script("migrate-compose-resources", "analyze_resources.py")
        audit = self.temporary / "audit.json"
        before = (root / "legacy/ui/src/commonMain/composeResources/values/strings.xml").read_text()
        run(script, "audit", "--root", root, "--json-out", audit)
        payload = load_json(audit)
        assert_valid_artifact(self, payload, "resource-audit")
        self.assertEqual(2, len(payload["definitions"]))
        self.assertEqual(1, len(payload["cross_module_usages"]))
        spec = write_json(self.temporary / "resources.json", {
            "schema_version": 1,
            "moves": [{"type": "string", "key": "orders_title", "from_module": ":legacy:ui", "to_module": ":feature:orders:ui", "preserve_key": True}],
        })
        plan = self.temporary / "plan.json"
        run(script, "plan", "--root", root, "--audit", audit, "--spec", spec, "--json-out", plan)
        plan_payload = load_json(plan)
        assert_valid_artifact(self, plan_payload, "resource-migration-plan")
        self.assertEqual(2, len(plan_payload["moves"][0]["definitions"]))
        self.assertEqual(before, (root / "legacy/ui/src/commonMain/composeResources/values/strings.xml").read_text())


class PersistenceMigrationTests(PackTestCase):
    def test_room_datastore_and_schema_baseline(self) -> None:
        root = self.temporary / "repo"
        write_module(root, ":core:data")
        write_module(root, ":feature:orders:data")
        write(
            root / "core/data/src/commonMain/kotlin/com/example/data/Database.kt",
            "package com.example.data\n@Database(entities = [OrderEntity::class], version = 12) abstract class AppDatabase : RoomDatabase()\n@Entity(tableName = \"orders\") data class OrderEntity(@ColumnInfo(name = \"order_id\") val id: String)\nval selected = stringPreferencesKey(\"selected_order\")\n",
        )
        write(root / "schemas/com.example.AppDatabase/12.json", '{"formatVersion": 1, "database": {"version": 12}}\n')
        rules = write_json(self.temporary / "persistence.json", {
            "schema_version": 1,
            "target_module": ":feature:orders:data",
            "allowed_modules": [":core:data", ":feature:orders:data"],
            "preserve_schema": True,
            "expected_database_versions": {"AppDatabase": 12},
            "required_schema_paths": ["schemas/com.example.AppDatabase/12.json"],
        })
        script = skill_script("migrate-kotlin-persistence-boundaries", "analyze_persistence.py")
        audit = self.temporary / "audit.json"
        run(script, "audit", "--root", root, "--rules", rules, "--json-out", audit)
        payload = load_json(audit)
        assert_valid_artifact(self, payload, "persistence-boundary-audit")
        self.assertEqual(12, payload["database_versions"]["AppDatabase"])
        identities = {(item["kind"], item["value"]) for item in payload["stored_identities"]}
        self.assertIn(("table", "orders"), identities)
        self.assertIn(("column", "order_id"), identities)
        self.assertIn(("preference-key", "selected_order"), identities)
        plan = self.temporary / "plan.json"
        run(script, "plan", "--root", root, "--audit", audit, "--rules", rules, "--json-out", plan)
        plan_payload = load_json(plan)
        assert_valid_artifact(self, plan_payload, "persistence-migration-plan")
        self.assertEqual("review", plan_payload["gates"]["plan_ready"])


class ModuleConsolidationTests(PackTestCase):
    def test_simulation_plan_and_final_check(self) -> None:
        root = self.temporary / "repo"
        modules = [":feature:orders:domain", ":feature:orders:navigation", ":app"]
        write_module(root, ":feature:orders:domain")
        write_module(root, ":feature:orders:navigation", [":feature:orders:domain"])
        write_module(root, ":app", [":feature:orders:navigation"])
        write_settings(root, modules)
        write(root / "feature/orders/domain/src/commonMain/kotlin/com/example/orders/Order.kt", "package com.example.orders\ninterface Order\n")
        write(root / "feature/orders/navigation/src/commonMain/kotlin/com/example/orders/nav/OrderDestination.kt", "package com.example.orders.nav\nobject OrderDestination\n")
        spec = write_json(self.temporary / "consolidate.json", {
            "schema_version": 1,
            "source_modules": [":feature:orders:domain", ":feature:orders:navigation"],
            "target_module": ":feature:orders:domain",
            "reason": "Same stable contract and measured task overhead",
            "evidence": {"build_metrics": "comparison.json", "ownership": "same"},
            "preserve_public_api": True,
            "preserve_schema": True,
        })
        script = skill_script("consolidate-kotlin-modules", "consolidate_modules.py")
        audit = self.temporary / "audit.json"
        run(script, "audit", "--root", root, "--spec", spec, "--json-out", audit)
        payload = load_json(audit)
        assert_valid_artifact(self, payload, "module-consolidation-audit")
        self.assertEqual([], payload["unresolved"])
        self.assertEqual([":feature:orders:domain"], payload["graph_after"][":app"])
        plan = self.temporary / "plan.json"
        run(script, "plan", "--root", root, "--audit", audit, "--spec", spec, "--json-out", plan)
        plan_payload = load_json(plan)
        assert_valid_artifact(self, plan_payload, "module-consolidation-plan")
        self.assertEqual(7, len(plan_payload["actions"]))
        run(script, "check", "--root", root, "--spec", spec, expected=1)

        shutil.rmtree(root / "feature/orders/navigation")
        write_module(root, ":app", [":feature:orders:domain"])
        write_settings(root, [":feature:orders:domain", ":app"])
        final = self.temporary / "check.json"
        run(script, "check", "--root", root, "--spec", spec, "--json-out", final)
        final_payload = load_json(final)
        assert_valid_artifact(self, final_payload, "module-consolidation-check")
        self.assertEqual("pass", final_payload["gates"]["retirement"])


class PackIntegrationTests(PackTestCase):
    def test_manifest_orchestrator_and_docs_include_all_new_skills(self) -> None:
        manifest = load_json(PACK / "skill-pack.json")
        orchestrator = (PACK / "modularize-kotlin-codebase/SKILL.md").read_text()
        readme = (PACK / "README.md").read_text()
        new_skills = {
            "integrate-kotlin-feature",
            "modularize-kotlin-dependency-injection",
            "decouple-kotlin-features",
            "migrate-kotlin-data-boundaries",
            "migrate-kotlin-tests",
            "migrate-compose-resources",
            "migrate-kotlin-persistence-boundaries",
            "consolidate-kotlin-modules",
        }
        self.assertTrue(new_skills.issubset(manifest["skills"]))
        for skill in new_skills:
            self.assertIn(f"${skill}", orchestrator)
            self.assertIn(f"${skill}", readme)
