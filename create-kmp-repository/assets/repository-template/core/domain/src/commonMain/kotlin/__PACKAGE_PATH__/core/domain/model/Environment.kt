package @@PACKAGE@@.core.domain.model

data class EnvironmentProfile(
    val id: String,
    val isProduction: Boolean,
    val isDebuggable: Boolean,
)

object Environment {
    private var configuredProfile: EnvironmentProfile? = null

    val current: EnvironmentProfile
        get() = checkNotNull(configuredProfile) { "Environment has not been configured." }

    fun configure(id: String, isDebuggable: Boolean) {
        require(id == "dev" || id == "prod") { "Unknown environment: $id" }
        val selected = EnvironmentProfile(
            id = id,
            isProduction = id == "prod",
            isDebuggable = isDebuggable,
        )
        check(configuredProfile == null || configuredProfile == selected) {
            "Environment is already configured as ${configuredProfile?.id}."
        }
        configuredProfile = selected
    }
}
