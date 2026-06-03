package com.calorieai.app.ui.navigation

import androidx.compose.material3.Icon
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.res.stringResource

@Composable
fun BottomNavBar(
    currentRoute: String?,
    onItemSelected: (Screen) -> Unit
) {
    NavigationBar {
        Screen.bottomItems.forEach { screen ->
            val selected = currentRoute == screen.route
            NavigationBarItem(
                selected = selected,
                onClick = { onItemSelected(screen) },
                icon = {
                    Icon(
                        imageVector = screen.icon,
                        contentDescription = stringResource(screen.labelRes)
                    )
                },
                label = { Text(stringResource(screen.labelRes)) },
                alwaysShowLabel = true
            )
        }
    }
}
