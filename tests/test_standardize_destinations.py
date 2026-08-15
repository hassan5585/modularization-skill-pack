"""Tests for standardize-kotlin-destinations (audit / plan / scaffold / check)."""

from __future__ import annotations

import sys
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

from helpers import PACK, PackTestCase, load_json, run, skill_script, write

SCRIPT = skill_script("standardize-kotlin-destinations", "standardize_destinations.py")


def _nav3_module(root: Path) -> None:
    write(
        root / "settings.gradle.kts",
        'rootProject.name = "destinations"\ninclude(":core:navigation", ":feature:orders:navigation", ":feature:orders:ui")\n',
    )
    write(
        root / "core" / "navigation" / "build.gradle.kts",
        """
plugins { kotlin("multiplatform") }
kotlin {
    androidTarget()
    iosArm64()
    sourceSets.commonMain.dependencies {
        implementation("org.jetbrains.androidx.navigation3:navigation3-runtime:1.1.1")
    }
}
""".strip()
        + "\n",
    )
    write(root / "feature" / "orders" / "navigation" / "build.gradle.kts", "plugins { kotlin(\"multiplatform\") }\n")
    write(root / "feature" / "orders" / "ui" / "build.gradle.kts", "plugins { kotlin(\"multiplatform\") }\n")


def _approute_fixture(root: Path) -> None:
    _nav3_module(root)
    write(
        root / "core" / "navigation" / "src" / "commonMain" / "kotlin" / "com" / "example" / "core" / "navigation" / "AppRoute.kt",
        """
package com.example.core.navigation

import kotlinx.serialization.Serializable

@Serializable
sealed interface AppRoute {
    @Serializable data object Home : AppRoute
    @Serializable data class Detail(val id: String) : AppRoute
}
""".strip()
        + "\n",
    )


def _compliant_fixture(root: Path) -> None:
    _nav3_module(root)
    write(
        root / "core" / "navigation" / "src" / "commonMain" / "kotlin" / "com" / "example" / "core" / "navigation" / "Destination.kt",
        """
package com.example.core.navigation

import androidx.navigation3.runtime.NavKey

interface Destination : NavKey {
    val destinationId: String
}
""".strip()
        + "\n",
    )
    write(
        root / "feature" / "orders" / "navigation" / "src" / "commonMain" / "kotlin" / "com" / "example" / "orders" / "navigation" / "OrdersDestination.kt",
        """
package com.example.orders.navigation

import com.example.core.navigation.Destination
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

@Serializable
sealed interface OrdersDestination : Destination {
    override val destinationId: String
        get() = when (this) {
            Root -> "orders.root"
            Landing -> "orders.landing"
            is Detail -> "orders.detail"
        }

    @Serializable
    @SerialName("orders.root")
    data object Root : OrdersDestination

    @Serializable
    @SerialName("orders.landing")
    data object Landing : OrdersDestination

    @Serializable
    @SerialName("orders.detail")
    data class Detail(val orderId: String) : OrdersDestination
}
""".strip()
        + "\n",
    )
    write(
        root / "feature" / "orders" / "navigation" / "src" / "commonMain" / "kotlin" / "com" / "example" / "orders" / "navigation" / "OrdersDestinationSerializers.kt",
        """
package com.example.orders.navigation

import com.example.core.navigation.Destination
import kotlinx.serialization.modules.PolymorphicModuleBuilder
import kotlinx.serialization.modules.subclass

fun PolymorphicModuleBuilder<Destination>.registerOrdersDestinationSerializers() {
    subclass(OrdersDestination.Root.serializer())
    subclass(OrdersDestination.Landing.serializer())
    subclass(OrdersDestination.Detail.serializer())
}
""".strip()
        + "\n",
    )


def _nav2_only_fixture(root: Path) -> None:
    write(root / "settings.gradle.kts", 'rootProject.name = "nav2"\ninclude(":app")\n')
    write(
        root / "app" / "build.gradle.kts",
        'dependencies { implementation("androidx.navigation:navigation-compose:2.8.0") }\n',
    )
    write(
        root / "app" / "src" / "main" / "kotlin" / "com" / "example" / "AppNav.kt",
        """
package com.example
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
@Composable
fun AppNav() {
    NavHost(navController, startDestination = "home") {
        composable("home") { }
    }
}
""".strip()
        + "\n",
    )


class StandardizeDestinationsTests(PackTestCase):
    def test_example_spec_and_artifact_kinds(self) -> None:
        sys.path.insert(0, str(PACK))
        from common.artifact_schema import ARTIFACT_KINDS, validate_artifact

        self.assertIn("destination-audit", ARTIFACT_KINDS)
        self.assertIn("destination-spec", ARTIFACT_KINDS)
        self.assertIn("destination-check", ARTIFACT_KINDS)
        spec = load_json(
            PACK / "standardize-kotlin-destinations" / "assets" / "destination-spec.example.json"
        )
        self.assertEqual([], validate_artifact(spec, "destination-spec"))

    def test_audit_and_plan_missing_destination(self) -> None:
        root = self.temporary / "missing"
        root.mkdir()
        _approute_fixture(root)
        audit_path = self.temporary / "audit.json"
        run(SCRIPT, "audit", "--root", str(root), "--json-out", str(audit_path))
        audit = load_json(audit_path)
        self.assertEqual(1, audit["schema_version"])
        self.assertIsNone(audit["contract"])
        self.assertTrue(any(base["name"] == "AppRoute" for base in audit["bases"]))
        self.assertTrue(any(leaf["name"] == "Home" for leaf in audit["leaves"]))
        self.assertTrue(any(item["rule"] == "missing-destination-contract" for item in audit["findings"]))
        self.assertTrue(any(item["rule"] == "missing-serial-name" for item in audit["findings"]))

        spec_path = self.temporary / "spec.json"
        run(SCRIPT, "plan", "--root", str(root), "--audit", str(audit_path), "--json-out", str(spec_path))
        spec = load_json(spec_path)
        self.assertTrue(spec["destination"]["introduce"])
        self.assertEqual(":core:navigation", spec["destination"]["module_path"])
        self.assertEqual("com.example.core.navigation", spec["destination"]["package"])
        self.assertEqual("commonMain", spec["destination"]["source_set"])
        self.assertTrue(any(item["from"] == "AppRoute" for item in spec["conversions"]))

    def test_scaffold_writes_destination_and_refuses_overwrite(self) -> None:
        root = self.temporary / "scaffold"
        root.mkdir()
        _approute_fixture(root)
        audit_path = self.temporary / "a.json"
        spec_path = self.temporary / "s.json"
        run(SCRIPT, "audit", "--root", str(root), "--json-out", str(audit_path))
        run(SCRIPT, "plan", "--root", str(root), "--audit", str(audit_path), "--json-out", str(spec_path))
        preview = run(SCRIPT, "scaffold", "--root", str(root), "--spec", str(spec_path))
        self.assertIn("Dry run", preview.stdout)
        dest = (
            root
            / "core"
            / "navigation"
            / "src"
            / "commonMain"
            / "kotlin"
            / "com"
            / "example"
            / "core"
            / "navigation"
            / "Destination.kt"
        )
        self.assertFalse(dest.exists())
        run(SCRIPT, "scaffold", "--root", str(root), "--spec", str(spec_path), "--apply")
        self.assertTrue(dest.is_file())
        text = dest.read_text(encoding="utf-8")
        self.assertIn("interface Destination : NavKey", text)
        self.assertIn("val destinationId: String", text)
        serializers = dest.with_name("DestinationSerializers.kt")
        self.assertTrue(serializers.is_file())
        self.assertIn("registerCoreDestinationSerializers", serializers.read_text(encoding="utf-8"))
        rejected = run(
            SCRIPT,
            "scaffold",
            "--root",
            str(root),
            "--spec",
            str(spec_path),
            "--apply",
            expected=3,
        )
        self.assertIn("refusing to overwrite", rejected.stderr)

    def test_compliant_check_passes(self) -> None:
        root = self.temporary / "ok"
        root.mkdir()
        _compliant_fixture(root)
        check_path = self.temporary / "check.json"
        result = run(SCRIPT, "check", "--root", str(root), "--json-out", str(check_path))
        self.assertIn("CHECK PASSED", result.stdout)
        payload = load_json(check_path)
        self.assertTrue(payload["summary"]["passed"])
        self.assertGreaterEqual(payload["summary"]["leaves"], 3)
        self.assertEqual("Destination", payload["contract"]["name"])

    def test_check_flags_complex_params_and_ui_ownership(self) -> None:
        root = self.temporary / "bad"
        root.mkdir()
        _nav3_module(root)
        write(
            root / "core" / "navigation" / "src" / "commonMain" / "kotlin" / "com" / "example" / "core" / "navigation" / "Destination.kt",
            """
package com.example.core.navigation
import androidx.navigation3.runtime.NavKey
interface Destination : NavKey {
    val destinationId: String
}
""".strip()
            + "\n",
        )
        write(
            root / "feature" / "orders" / "ui" / "src" / "commonMain" / "kotlin" / "com" / "example" / "orders" / "ui" / "OrdersDestination.kt",
            """
package com.example.orders.ui
import com.example.core.navigation.Destination
import kotlinx.serialization.Serializable
data class Order(val id: String)
@Serializable
data class Detail(val order: Order) : Destination {
    override val destinationId = "orders.detail"
}
""".strip()
            + "\n",
        )
        check_path = self.temporary / "bad-check.json"
        failed = run(SCRIPT, "check", "--root", str(root), "--json-out", str(check_path), expected=1)
        self.assertIn("CHECK FAILED", failed.stdout)
        payload = load_json(check_path)
        rules = {item["rule"] for item in payload["findings"]}
        self.assertIn("non-primitive-params", rules)
        self.assertIn("destination-in-ui", rules)
        self.assertIn("missing-serial-name", rules)
        self.assertIn("unregistered-serializer", rules)

    def test_nav2_only_blocks_scaffold(self) -> None:
        root = self.temporary / "nav2"
        root.mkdir()
        _nav2_only_fixture(root)
        audit_path = self.temporary / "nav2-audit.json"
        run(SCRIPT, "audit", "--root", str(root), "--json-out", str(audit_path))
        audit = load_json(audit_path)
        self.assertTrue(any(item["rule"] == "navigation3-required" for item in audit["findings"]))
        spec_path = self.temporary / "nav2-spec.json"
        run(SCRIPT, "plan", "--root", str(root), "--audit", str(audit_path), "--json-out", str(spec_path))
        rejected = run(
            SCRIPT,
            "scaffold",
            "--root",
            str(root),
            "--spec",
            str(spec_path),
            expected=2,
        )
        self.assertTrue(
            "Navigation 3" in rejected.stderr or "navigation3_runtime" in rejected.stderr
        )

    def test_existing_destination_skips_scaffold(self) -> None:
        root = self.temporary / "exists"
        root.mkdir()
        _compliant_fixture(root)
        audit_path = self.temporary / "exists-audit.json"
        spec_path = self.temporary / "exists-spec.json"
        run(SCRIPT, "audit", "--root", str(root), "--json-out", str(audit_path))
        run(SCRIPT, "plan", "--root", str(root), "--audit", str(audit_path), "--json-out", str(spec_path))
        spec = load_json(spec_path)
        self.assertFalse(spec["destination"]["introduce"])
        preview = run(SCRIPT, "scaffold", "--root", str(root), "--spec", str(spec_path))
        self.assertIn("already exists", preview.stdout)
