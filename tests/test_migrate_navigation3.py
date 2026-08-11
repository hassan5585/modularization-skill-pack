"""Tests for migrate-to-navigation3 (audit / plan / scaffold / check)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

from helpers import PACK, PackTestCase, load_json, run, skill_script, write

SCRIPT = skill_script("migrate-to-navigation3", "migrate_navigation3.py")


def _android_typed_fixture(root: Path) -> None:
    write(
        root / "settings.gradle.kts",
        'rootProject.name = "nav2-android"\ninclude(":app", ":core:navigation")\n',
    )
    write(
        root / "app" / "build.gradle.kts",
        """
plugins { id("com.android.application") }
dependencies {
    implementation("androidx.navigation:navigation-compose:2.8.0")
    implementation(project(":core:navigation"))
}
""".strip()
        + "\n",
    )
    write(
        root / "core" / "navigation" / "build.gradle.kts",
        """
plugins { id("com.android.library") }
dependencies {
    implementation("androidx.navigation:navigation-compose:2.8.0")
}
""".strip()
        + "\n",
    )
    write(
        root / "core" / "navigation" / "src" / "main" / "kotlin" / "com" / "example" / "core" / "navigation" / "AppRoute.kt",
        """
package com.example.core.navigation

import kotlinx.serialization.Serializable

@Serializable
sealed interface AppRoute {
    @Serializable data object Home : AppRoute
    @Serializable data class Detail(val id: String) : AppRoute
    @Serializable data object SettingsGraph : AppRoute
}
""".strip()
        + "\n",
    )
    write(
        root / "app" / "src" / "main" / "kotlin" / "com" / "example" / "app" / "MainActivity.kt",
        """
package com.example.app

import androidx.compose.runtime.Composable
import androidx.navigation.NavHostController
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.dialog
import androidx.navigation.compose.navigation
import androidx.navigation.compose.rememberNavController
import androidx.navigation.navDeepLink
import androidx.navigation.toRoute
import com.example.core.navigation.AppRoute

@Composable
fun AppNav() {
    val navController = rememberNavController()
    NavHost(navController = navController, startDestination = AppRoute.Home) {
        composable<AppRoute.Home> { HomeScreen(navController) }
        navigation<AppRoute.SettingsGraph>(startDestination = AppRoute.Detail("0")) {
            composable<AppRoute.Detail>(
                deepLinks = listOf(navDeepLink { uriPattern = "app://detail/{id}" }),
            ) { entry ->
                val route = entry.toRoute<AppRoute.Detail>()
                DetailScreen(route.id, navController)
            }
        }
        dialog<AppRoute.Home> { /* confirm */ }
    }
}

@Composable
fun HomeScreen(navController: NavHostController) {
    navController.navigate(AppRoute.Detail("1")) {
        launchSingleTop = true
        popUpTo(AppRoute.Home) { inclusive = false }
    }
    navController.previousBackStackEntry?.savedStateHandle?.set("result", true)
}

@Composable
fun DetailScreen(id: String, navController: NavHostController) {
    navController.navigateUp()
    val owner = navController.getBackStackEntry(AppRoute.SettingsGraph)
}
""".strip()
        + "\n",
    )
    write(
        root / "app" / "src" / "main" / "kotlin" / "com" / "example" / "app" / "HomeViewModel.kt",
        """
package com.example.app

import androidx.lifecycle.ViewModel
import androidx.navigation.NavController

class HomeViewModel(
    private val navController: NavController,
) : ViewModel() {
    fun open() {
        navController.popBackStack()
    }
}
""".strip()
        + "\n",
    )


def _android_string_fixture(root: Path) -> None:
    write(root / "settings.gradle.kts", 'rootProject.name = "nav2-string"\ninclude(":app")\n')
    write(
        root / "app" / "build.gradle.kts",
        'dependencies { implementation("androidx.navigation:navigation-compose:2.7.7") }\n',
    )
    write(
        root / "app" / "src" / "main" / "kotlin" / "com" / "example" / "StringNav.kt",
        """
package com.example

import androidx.compose.runtime.Composable
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController

@Composable
fun StringNav() {
    val navController = rememberNavController()
    NavHost(navController, startDestination = "home") {
        composable("home") { }
        composable("detail/{id}") { }
    }
    navController.navigate("detail/1")
}
""".strip()
        + "\n",
    )


def _kmp_fixture(root: Path) -> None:
    write(
        root / "settings.gradle.kts",
        'rootProject.name = "nav2-kmp"\ninclude(":composeApp", ":core:navigation")\n',
    )
    write(
        root / "composeApp" / "build.gradle.kts",
        """
plugins { kotlin("multiplatform"); id("org.jetbrains.compose") }
kotlin {
    androidTarget()
    iosArm64()
    sourceSets {
        commonMain.dependencies {
            implementation("org.jetbrains.androidx.navigation:navigation-compose:2.8.0")
            implementation(project(":core:navigation"))
        }
    }
}
""".strip()
        + "\n",
    )
    write(
        root / "core" / "navigation" / "build.gradle.kts",
        """
plugins { kotlin("multiplatform") }
kotlin {
    androidTarget()
    iosArm64()
    sourceSets.commonMain.dependencies {
        implementation("org.jetbrains.androidx.navigation:navigation-compose:2.8.0")
    }
}
""".strip()
        + "\n",
    )
    write(
        root / "core" / "navigation" / "src" / "commonMain" / "kotlin" / "com" / "example" / "core" / "navigation" / "AppRoute.kt",
        """
package com.example.core.navigation

import kotlinx.serialization.Serializable

@Serializable
sealed interface AppRoute {
    @Serializable data object Home : AppRoute
    @Serializable data class Profile(val userId: String) : AppRoute
}
""".strip()
        + "\n",
    )
    write(
        root / "composeApp" / "src" / "commonMain" / "kotlin" / "com" / "example" / "App.kt",
        """
package com.example

import androidx.compose.material3.NavigationBar
import androidx.compose.runtime.Composable
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import androidx.navigation.toRoute
import com.example.core.navigation.AppRoute

@Composable
fun App() {
    val homeNav = rememberNavController()
    val profileNav = rememberNavController()
    NavigationBar { }
    NavHost(homeNav, startDestination = AppRoute.Home) {
        composable<AppRoute.Home> { }
        composable<AppRoute.Profile> { entry -> entry.toRoute<AppRoute.Profile>() }
    }
    NavHost(profileNav, startDestination = AppRoute.Profile("x")) {
        composable<AppRoute.Profile> { }
    }
}

object NavSerializers {
    // placeholder — incomplete until migration
}
""".strip()
        + "\n",
    )


def _fragment_fixture(root: Path) -> None:
    write(root / "settings.gradle.kts", 'rootProject.name = "fragments"\ninclude(":app")\n')
    write(
        root / "app" / "build.gradle.kts",
        'dependencies { implementation("androidx.navigation:navigation-fragment-ktx:2.7.7") }\n',
    )
    write(
        root / "app" / "src" / "main" / "res" / "navigation" / "nav_graph.xml",
        """
<?xml version="1.0" encoding="utf-8"?>
<navigation xmlns:android="http://schemas.android.com/apk/res/android"
    xmlns:app="http://schemas.android.com/apk/res-auto"
    app:startDestination="@id/home">
    <fragment android:id="@+id/home" android:name="com.example.HomeFragment" />
</navigation>
""".strip()
        + "\n",
    )
    write(
        root / "app" / "src" / "main" / "kotlin" / "com" / "example" / "MainActivity.kt",
        """
package com.example
import androidx.navigation.fragment.NavHostFragment
class MainActivity {
    fun x(host: NavHostFragment) {}
}
""".strip()
        + "\n",
    )


class MigrateNavigation3Tests(PackTestCase):
    def test_typed_android_audit_and_plan_apis(self) -> None:
        root = self.temporary / "typed-android"
        root.mkdir()
        _android_typed_fixture(root)
        audit_path = self.temporary / "audit.json"
        run(SCRIPT, "audit", "--root", str(root), "--json-out", str(audit_path))
        audit = load_json(audit_path)
        self.assertEqual(1, audit["schema_version"])
        self.assertEqual("android", audit["project"]["platform"])
        self.assertEqual("androidx", audit["project"]["navigation_coordinates"])
        self.assertEqual("typed", audit["routes"]["style"])
        self.assertTrue(audit["behavior"]["launch_single_top"])
        self.assertTrue(audit["behavior"]["pop_up_to"])
        self.assertTrue(audit["behavior"]["transient_results"])
        self.assertTrue(audit["behavior"]["deep_link_routing"])
        self.assertTrue(audit["behavior"]["nested_graphs"])
        self.assertTrue(audit["behavior"]["dialogs"])
        self.assertTrue(audit["behavior"]["graph_view_model_scope"] or audit["behavior"]["entry_view_model_scope"])
        self.assertTrue(any(b["name"] == "AppRoute" for b in audit["routes"]["bases"]))
        self.assertEqual("pass", audit["gates"]["unsupported_scope"])
        self.assertTrue(any(f["rule"] == "nav-controller-leak" for f in audit["findings"]))

        spec_path = self.temporary / "spec.json"
        run(
            SCRIPT,
            "plan",
            "--root",
            str(root),
            "--audit",
            str(audit_path),
            "--json-out",
            str(spec_path),
        )
        spec = load_json(spec_path)
        self.assertEqual("AppRoute", spec["route_model"]["contract_type"])
        self.assertFalse(spec["route_model"]["requires_string_to_typed_phase"])
        self.assertTrue(spec["navigator"]["apis"]["navigate"])
        self.assertTrue(spec["navigator"]["apis"]["back"])
        self.assertTrue(spec["navigator"]["apis"]["launch_single_top"])
        self.assertTrue(spec["navigator"]["apis"]["pop_up_to"])
        self.assertTrue(spec["navigator"]["apis"]["transient_results"])
        self.assertEqual(":core:navigation", spec["navigator"]["module_path"])
        self.assertEqual("com.example.core.navigation", spec["navigator"]["package"])

    def test_string_routes_require_typed_phase(self) -> None:
        root = self.temporary / "string-android"
        root.mkdir()
        _android_string_fixture(root)
        audit_path = self.temporary / "audit-string.json"
        run(SCRIPT, "audit", "--root", str(root), "--json-out", str(audit_path))
        audit = load_json(audit_path)
        self.assertEqual("string", audit["routes"]["style"])
        self.assertTrue(
            any(f["rule"] == "string-routes-require-typed-phase" for f in audit["findings"])
        )
        spec_path = self.temporary / "spec-string.json"
        run(SCRIPT, "plan", "--root", str(root), "--audit", str(audit_path), "--json-out", str(spec_path))
        spec = load_json(spec_path)
        self.assertTrue(spec["route_model"]["requires_string_to_typed_phase"])
        self.assertEqual("fail", spec["gates"]["string_to_typed"])
        self.assertTrue(any(u["id"] == "string-to-typed" for u in spec["unresolved"]))

    def test_kmp_common_main_and_multiple_stacks(self) -> None:
        root = self.temporary / "kmp"
        root.mkdir()
        _kmp_fixture(root)
        audit_path = self.temporary / "audit-kmp.json"
        run(SCRIPT, "audit", "--root", str(root), "--json-out", str(audit_path))
        audit = load_json(audit_path)
        self.assertEqual("kmp", audit["project"]["platform"])
        self.assertEqual("jetbrains", audit["project"]["navigation_coordinates"])
        self.assertIn("commonMain", audit["project"]["source_sets"])
        self.assertEqual("typed", audit["routes"]["style"])
        self.assertTrue(audit["behavior"]["multiple_stacks"] or audit["behavior"]["bottom_nav"])
        self.assertTrue(
            any(f["rule"] == "multiple-back-stacks" for f in audit["findings"])
            or audit["behavior"]["multiple_stacks"]
        )
        spec_path = self.temporary / "spec-kmp.json"
        run(SCRIPT, "plan", "--root", str(root), "--audit", str(audit_path), "--json-out", str(spec_path))
        spec = load_json(spec_path)
        self.assertEqual("jetbrains", spec["project"]["navigation_coordinates"])
        self.assertTrue(
            any("jetbrains" in c for c in spec["dependencies"]["navigation3_recommended"])
        )
        self.assertEqual("commonMain", spec["navigator"]["source_set"])

    def test_fragment_xml_rejected(self) -> None:
        root = self.temporary / "fragments"
        root.mkdir()
        _fragment_fixture(root)
        audit_path = self.temporary / "audit-frag.json"
        run(SCRIPT, "audit", "--root", str(root), "--json-out", str(audit_path))
        audit = load_json(audit_path)
        self.assertEqual("fail", audit["gates"]["unsupported_scope"])
        self.assertTrue(any(f["rule"] == "unsupported-scope" for f in audit["findings"]))
        spec_path = self.temporary / "spec-frag.json"
        run(SCRIPT, "plan", "--root", str(root), "--audit", str(audit_path), "--json-out", str(spec_path))
        spec = load_json(spec_path)
        self.assertEqual("fail", spec["gates"]["unsupported_scope"])
        rejected = run(
            SCRIPT,
            "scaffold",
            "--root",
            str(root),
            "--spec",
            str(spec_path),
            expected=2,
        )
        self.assertIn("unsupported_scope", rejected.stderr)

    def test_scaffold_approute_and_navkey_fallback(self) -> None:
        root = self.temporary / "scaffold-app"
        root.mkdir()
        _android_typed_fixture(root)
        audit_path = self.temporary / "a.json"
        spec_path = self.temporary / "s.json"
        run(SCRIPT, "audit", "--root", str(root), "--json-out", str(audit_path))
        run(SCRIPT, "plan", "--root", str(root), "--audit", str(audit_path), "--json-out", str(spec_path))
        # Clear blocking unresolved for module (exists) — package may still need force for package-inferred only
        spec = load_json(spec_path)
        # Ensure clean gates for scaffold: remove non-blocking unresolved that might block
        spec["unresolved"] = [u for u in spec["unresolved"] if u["id"] not in {"string-to-typed"}]
        # navigation module exists so blocking should be empty
        blocking = [u for u in spec["unresolved"] if u["id"] in {"unsupported-scope", "package-unknown", "navigation-module-missing"}]
        self.assertEqual([], blocking)
        spec_path.write_text(json.dumps(spec), encoding="utf-8")

        preview = run(SCRIPT, "scaffold", "--root", str(root), "--spec", str(spec_path))
        self.assertIn("Dry run", preview.stdout)
        navigator_path = (
            root
            / "core"
            / "navigation"
            / "src"
            / "main"
            / "kotlin"
            / "com"
            / "example"
            / "core"
            / "navigation"
            / "Navigator.kt"
        )
        self.assertFalse(navigator_path.exists())

        run(SCRIPT, "scaffold", "--root", str(root), "--spec", str(spec_path), "--apply")
        self.assertTrue(navigator_path.is_file())
        text = navigator_path.read_text(encoding="utf-8")
        self.assertIn("interface Navigator", text)
        self.assertIn("AppRoute", text)
        self.assertNotIn("com.ysn", text)
        self.assertNotIn("interface Destination", text)
        self.assertIn("fun navigate", text)
        self.assertIn("fun popBackStack", text)
        self.assertIn("NavOptions", text)
        options = (
            root
            / "core"
            / "navigation"
            / "src"
            / "main"
            / "kotlin"
            / "com"
            / "example"
            / "core"
            / "navigation"
            / "NavOptions.kt"
        )
        self.assertTrue(options.is_file())
        recording = (
            root
            / "core"
            / "navigation"
            / "src"
            / "main"
            / "kotlin"
            / "com"
            / "example"
            / "core"
            / "navigation"
            / "RecordingNavigator.kt"
        )
        self.assertTrue(recording.is_file())
        recording_text = recording.read_text(encoding="utf-8")
        self.assertIn("class RecordingNavigator", recording_text)
        self.assertNotIn("com.ysn.core.navigation.Destination", recording_text)

        # conflict refusal
        run(
            SCRIPT,
            "scaffold",
            "--root",
            str(root),
            "--spec",
            str(spec_path),
            "--apply",
            expected=3,
        )

        # NavKey fallback when no base type
        root2 = self.temporary / "scaffold-navkey"
        root2.mkdir()
        write(root2 / "settings.gradle.kts", 'rootProject.name = "x"\ninclude(":core:navigation")\n')
        write(root2 / "core" / "navigation" / "build.gradle.kts", "plugins {}\n")
        write(
            root2
            / "app"
            / "src"
            / "main"
            / "kotlin"
            / "Host.kt",
            """
package com.example
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.rememberNavController
import androidx.compose.runtime.Composable
@Composable
fun H() {
  val c = rememberNavController()
  NavHost(c, "home") { }
}
""".strip()
            + "\n",
        )
        write(
            root2 / "app" / "build.gradle.kts",
            'dependencies { implementation("androidx.navigation:navigation-compose:2.8.0") }\n',
        )
        navkey_spec = {
            "schema_version": 1,
            "project": {"platform": "android", "navigation_coordinates": "androidx"},
            "route_model": {
                "style": "string",
                "existing_base_type": None,
                "contract_type": "NavKey",
                "contract_import": "androidx.navigation3.runtime.NavKey",
                "requires_string_to_typed_phase": True,
                "serialization": {
                    "uses_kotlinx_serialization": False,
                    "polymorphic_registration_required": False,
                },
            },
            "navigator": {
                "module_path": ":core:navigation",
                "module_directory": "core/navigation",
                "package": "com.example.core.navigation",
                "source_set": "main",
                "interface_name": "Navigator",
                "existing_navigator": None,
                "apis": {
                    "navigate": True,
                    "back": True,
                    "navigate_up": False,
                    "launch_single_top": False,
                    "pop_up_to": False,
                    "current_route_flow": False,
                    "previous_route_flow": False,
                    "transient_results": False,
                    "readiness": False,
                    "deep_link_routing": False,
                    "graph_view_model_scope": False,
                    "entry_view_model_scope": False,
                    "reset_session": False,
                },
                "files": {
                    "navigator": "Navigator.kt",
                    "nav_options": None,
                    "recording_fake": "RecordingNavigator.kt",
                    "recording_fake_module": None,
                },
            },
            "migration_phases": ["audit", "plan", "extract_navigator"],
            "gates": {"unsupported_scope": "pass"},
            "unresolved": [],
        }
        navkey_path = self.temporary / "navkey-spec.json"
        navkey_path.write_text(json.dumps(navkey_spec), encoding="utf-8")
        run(SCRIPT, "scaffold", "--root", str(root2), "--spec", str(navkey_path), "--apply")
        nav_text = (
            root2
            / "core"
            / "navigation"
            / "src"
            / "main"
            / "kotlin"
            / "com"
            / "example"
            / "core"
            / "navigation"
            / "Navigator.kt"
        ).read_text(encoding="utf-8")
        self.assertIn("NavKey", nav_text)
        self.assertNotIn("Destination", nav_text)
        self.assertNotIn("com.ysn", nav_text)
        self.assertNotIn("NavOptions", nav_text)  # selective API — no options file needed

    def test_scaffold_validation_and_selective_api(self) -> None:
        root = self.temporary / "validate"
        root.mkdir()
        write(root / "core" / "navigation" / "build.gradle.kts", "plugins {}\n")
        bad = {
            "schema_version": 1,
            "project": {"platform": "android"},
            "route_model": {
                "contract_type": "Destination",
                "contract_import": "com.example.Destination",
                "existing_base_type": None,
            },
            "navigator": {
                "module_path": ":core:navigation",
                "module_directory": "core/navigation",
                "package": "com.example.core.navigation",
                "source_set": "main",
                "interface_name": "Navigator",
                "apis": {"navigate": True, "back": True},
                "files": {"navigator": "Navigator.kt", "recording_fake": "RecordingNavigator.kt"},
            },
            "migration_phases": [],
            "gates": {"unsupported_scope": "pass"},
            "unresolved": [],
        }
        path = self.temporary / "bad-dest.json"
        path.write_text(json.dumps(bad), encoding="utf-8")
        rejected = run(SCRIPT, "scaffold", "--root", str(root), "--spec", str(path), expected=2)
        self.assertIn("Destination", rejected.stderr)

        bad_pkg = dict(bad)
        bad_pkg["route_model"] = {
            "contract_type": "NavKey",
            "contract_import": "androidx.navigation3.runtime.NavKey",
            "existing_base_type": None,
        }
        bad_pkg["navigator"] = dict(bad["navigator"])
        bad_pkg["navigator"]["package"] = "../evil"
        path.write_text(json.dumps(bad_pkg), encoding="utf-8")
        rejected = run(SCRIPT, "scaffold", "--root", str(root), "--spec", str(path), expected=2)
        self.assertIn("package", rejected.stderr.lower())

        escape = dict(bad_pkg)
        escape["navigator"] = dict(bad["navigator"])
        escape["navigator"]["package"] = "com.example.ok"
        escape["navigator"]["module_directory"] = "../outside"
        escape["route_model"] = bad_pkg["route_model"]
        path.write_text(json.dumps(escape), encoding="utf-8")
        rejected = run(SCRIPT, "scaffold", "--root", str(root), "--spec", str(path), expected=2)
        self.assertTrue(
            "module_directory" in rejected.stderr or "escapes" in rejected.stderr or "invalid" in rejected.stderr
        )

    def test_check_reports_leftovers_and_clean_nav3(self) -> None:
        root = self.temporary / "leftovers"
        root.mkdir()
        _android_typed_fixture(root)
        check_path = self.temporary / "check.json"
        failed = run(
            SCRIPT,
            "check",
            "--root",
            str(root),
            "--json-out",
            str(check_path),
            expected=1,
        )
        self.assertIn("CHECK FAILED", failed.stdout)
        report = load_json(check_path)
        rules = {f["rule"] for f in report["findings"]}
        self.assertTrue(
            "leftover-navigation2-dependency" in rules or "leftover-navigation2-import" in rules
        )
        self.assertTrue("leftover-navhost" in rules or "host-not-cut-over" in rules)
        self.assertIn("nav-controller-leak", rules)

        # Clean Nav3-style fixture
        clean = self.temporary / "clean-nav3"
        clean.mkdir()
        write(clean / "settings.gradle.kts", 'rootProject.name = "clean"\ninclude(":app")\n')
        write(
            clean / "app" / "build.gradle.kts",
            'dependencies { implementation("androidx.navigation3:navigation3-ui:1.0.0") }\n',
        )
        write(
            clean / "app" / "src" / "main" / "kotlin" / "com" / "example" / "Host.kt",
            """
package com.example

import androidx.compose.runtime.Composable
import androidx.navigation3.runtime.NavKey
import androidx.navigation3.ui.NavDisplay
import kotlinx.serialization.Serializable
import kotlinx.serialization.modules.SerializersModule
import kotlinx.serialization.modules.polymorphic
import kotlinx.serialization.modules.subclass

@Serializable
data object Home : NavKey

@Composable
fun Host() {
    NavDisplay(entries = emptyList(), onBack = {})
}

val module = SerializersModule {
    polymorphic(NavKey::class) {
        subclass(Home::class)
    }
}
""".strip()
            + "\n",
        )
        clean_check = self.temporary / "clean-check.json"
        # May still warn on missing host registration style detection — NavDisplay should be found
        result = run(
            SCRIPT,
            "check",
            "--root",
            str(clean),
            "--json-out",
            str(clean_check),
            expected=0,
        )
        self.assertIn("CHECK PASSED", result.stdout)
        clean_report = load_json(clean_check)
        self.assertTrue(clean_report["summary"]["passed"])

    def test_check_with_spec_flags_missing_serializers(self) -> None:
        root = self.temporary / "no-ser"
        root.mkdir()
        write(root / "settings.gradle.kts", 'rootProject.name = "n"\ninclude(":app")\n')
        write(
            root / "app" / "build.gradle.kts",
            'dependencies { implementation("org.jetbrains.androidx.navigation3:navigation3-ui:1.0.0") }\n',
        )
        write(
            root / "app" / "src" / "commonMain" / "kotlin" / "com" / "example" / "Host.kt",
            """
package com.example
import androidx.compose.runtime.Composable
import androidx.navigation3.ui.NavDisplay
@Composable
fun Host() { NavDisplay(entries = emptyList(), onBack = {}) }
""".strip()
            + "\n",
        )
        write(
            root / "core" / "navigation" / "src" / "commonMain" / "kotlin" / "com" / "example" / "AppRoute.kt",
            """
package com.example
interface AppRoute
""".strip()
            + "\n",
        )
        spec = {
            "schema_version": 1,
            "route_model": {
                "contract_type": "AppRoute",
                "existing_base_type": {
                    "name": "AppRoute",
                    "path": "core/navigation/src/commonMain/kotlin/com/example/AppRoute.kt",
                },
                "serialization": {
                    "uses_kotlinx_serialization": True,
                    "polymorphic_registration_required": True,
                },
            },
            "navigator": {},
            "back_stack": {},
        }
        spec_path = self.temporary / "ser-spec.json"
        spec_path.write_text(json.dumps(spec), encoding="utf-8")
        check_path = self.temporary / "ser-check.json"
        run(
            SCRIPT,
            "check",
            "--root",
            str(root),
            "--spec",
            str(spec_path),
            "--json-out",
            str(check_path),
            expected=1,
        )
        report = load_json(check_path)
        rules = {f["rule"] for f in report["findings"]}
        self.assertIn("missing-polymorphic-serializer-registration", rules)
        self.assertIn("missing-navkey-or-serializable", rules)

    def test_artifact_schema_kinds_registered(self) -> None:
        sys.path.insert(0, str(PACK))
        from common.artifact_schema import ARTIFACT_KINDS, envelope_fields, validate_artifact

        self.assertIn("navigation3-audit", ARTIFACT_KINDS)
        self.assertIn("navigation3-spec", ARTIFACT_KINDS)
        self.assertIn("navigation3-check", ARTIFACT_KINDS)
        payload = envelope_fields(skill="migrate-to-navigation3", script="migrate_navigation3.py")
        payload.update(
            {
                "project": {},
                "routes": {},
                "hosts": [],
                "findings": [],
            }
        )
        self.assertEqual([], validate_artifact(payload, "navigation3-audit"))

    def test_example_spec_validates(self) -> None:
        example = load_json(
            PACK / "migrate-to-navigation3" / "assets" / "navigation3-spec.example.json"
        )
        sys.path.insert(0, str(PACK))
        from common.artifact_schema import validate_artifact

        self.assertEqual([], validate_artifact(example, "navigation3-spec"))


if __name__ == "__main__":
    import unittest

    unittest.main()
