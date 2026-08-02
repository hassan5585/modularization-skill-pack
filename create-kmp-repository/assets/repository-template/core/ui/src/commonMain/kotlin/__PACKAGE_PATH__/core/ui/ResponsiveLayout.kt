package @@PACKAGE@@.core.ui

enum class AdaptiveWidthClass { Compact, Medium, Expanded, Large, ExtraLarge }
enum class AdaptiveHeightClass { Compact, Medium, Expanded }

data class ResponsiveLayout(
    val widthClass: AdaptiveWidthClass,
    val heightClass: AdaptiveHeightClass,
) {
    val canUseTwoPane: Boolean
        get() = widthClass >= AdaptiveWidthClass.Expanded && heightClass != AdaptiveHeightClass.Compact
}

fun responsiveLayout(widthDp: Int, heightDp: Int): ResponsiveLayout = ResponsiveLayout(
    widthClass = when {
        widthDp < 600 -> AdaptiveWidthClass.Compact
        widthDp < 840 -> AdaptiveWidthClass.Medium
        widthDp < 1200 -> AdaptiveWidthClass.Expanded
        widthDp < 1600 -> AdaptiveWidthClass.Large
        else -> AdaptiveWidthClass.ExtraLarge
    },
    heightClass = when {
        heightDp < 480 -> AdaptiveHeightClass.Compact
        heightDp < 900 -> AdaptiveHeightClass.Medium
        else -> AdaptiveHeightClass.Expanded
    },
)
