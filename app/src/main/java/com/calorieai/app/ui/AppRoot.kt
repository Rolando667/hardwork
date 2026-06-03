package com.calorieai.app.ui

import androidx.compose.animation.AnimatedContentTransitionScope
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Scaffold
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.navigation.NavDestination.Companion.hierarchy
import androidx.navigation.NavGraph.Companion.findStartDestination
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import com.calorieai.app.ui.add.AddScreen
import com.calorieai.app.ui.diary.DiaryScreen
import com.calorieai.app.ui.navigation.BottomNavBar
import com.calorieai.app.ui.navigation.Screen
import com.calorieai.app.ui.profile.ProfileScreen

/** Корінь застосунку: Scaffold з нижньою навігацією та NavHost. */
@Composable
fun AppRoot() {
    val navController = rememberNavController()
    val backStackEntry by navController.currentBackStackEntryAsState()
    val currentRoute = backStackEntry?.destination?.route

    Scaffold(
        bottomBar = {
            BottomNavBar(
                currentRoute = currentRoute,
                onItemSelected = { screen ->
                    navController.navigate(screen.route) {
                        popUpTo(navController.graph.findStartDestination().id) {
                            saveState = true
                        }
                        launchSingleTop = true
                        restoreState = true
                    }
                }
            )
        }
    ) { innerPadding ->
        NavHost(
            navController = navController,
            startDestination = Screen.Diary.route,
            modifier = Modifier.padding(innerPadding),
            enterTransition = {
                fadeIn(animationSpec = tween(250)) +
                    slideIntoContainer(AnimatedContentTransitionScope.SlideDirection.Up, tween(250))
            },
            exitTransition = { fadeOut(animationSpec = tween(150)) }
        ) {
            composable(Screen.Diary.route) { DiaryScreen() }
            composable(Screen.Add.route) {
                AddScreen(onSavedNavigateToDiary = {
                    navController.navigate(Screen.Diary.route) {
                        popUpTo(Screen.Diary.route) { inclusive = true }
                        launchSingleTop = true
                    }
                })
            }
            composable(Screen.Profile.route) { ProfileScreen() }
        }
    }
}
