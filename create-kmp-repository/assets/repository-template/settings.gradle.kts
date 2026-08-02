pluginManagement {
    repositories {
        google {
            content {
                includeGroupByRegex("com\\.android.*")
                includeGroupByRegex("com\\.google.*")
                includeGroupByRegex("androidx.*")
            }
        }
        mavenCentral()
        gradlePluginPortal()
    }
    includeBuild("plugins")
}

dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        google()
        mavenCentral()
    }
}

rootProject.name = "@@REPO_NAME@@"

include(":androidApp", ":composeApp")
include(":core", ":core:domain", ":core:data", ":core:navigation", ":core:ui")
include(
    ":feature:home",
    ":feature:home:domain",
    ":feature:home:data",
    ":feature:home:navigation",
    ":feature:home:ui",
    ":feature:home:test",
)
include(":util:platform", ":util:platform:domain", ":util:platform:real")
include(":test", ":test:core")
