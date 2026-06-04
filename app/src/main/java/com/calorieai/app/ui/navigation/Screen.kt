package com.calorieai.app.ui.navigation

import androidx.annotation.StringRes
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.MenuBook
import androidx.compose.material.icons.filled.AddCircle
import androidx.compose.material.icons.filled.BarChart
import androidx.compose.material.icons.filled.Person
import androidx.compose.ui.graphics.vector.ImageVector
import com.calorieai.app.R

/** Пункти нижньої навігації. */
enum class Screen(
    val route: String,
    @StringRes val labelRes: Int,
    val icon: ImageVector
) {
    Diary("diary", R.string.nav_diary, Icons.AutoMirrored.Filled.MenuBook),
    Add("add", R.string.nav_add, Icons.Filled.AddCircle),
    Stats("stats", R.string.nav_stats, Icons.Filled.BarChart),
    Profile("profile", R.string.nav_profile, Icons.Filled.Person);

    companion object {
        val bottomItems = listOf(Diary, Add, Stats, Profile)

        fun fromRoute(route: String?): Screen =
            entries.firstOrNull { it.route == route } ?: Diary
    }
}
