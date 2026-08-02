plugins {
    alias(libs.plugins.architecture.android.app)
}

dependencies {
    implementation(project(":composeApp"))
    implementation(project(":core:domain"))
    implementation(libs.androidx.activity.compose)
    implementation(libs.compose.runtime)
    implementation(libs.compose.ui)
    implementation(libs.compose.material3)
    debugImplementation(libs.compose.ui.tooling.preview)
}
