package com.calorieai.app.ui.profile

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import android.Manifest
import android.content.pm.PackageManager
import android.os.Build
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.core.content.ContextCompat
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Visibility
import androidx.compose.material.icons.filled.VisibilityOff
import androidx.compose.material3.Button
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.calorieai.app.R
import com.calorieai.app.domain.model.ActivityLevel
import com.calorieai.app.domain.model.Goal
import com.calorieai.app.domain.model.Sex
import com.calorieai.app.domain.model.ThemeMode

@OptIn(ExperimentalMaterial3Api::class, ExperimentalLayoutApi::class)
@Composable
fun ProfileScreen(
    viewModel: ProfileViewModel = hiltViewModel()
) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    val snackbarHostState = remember { SnackbarHostState() }
    val context = LocalContext.current
    var apiKeyVisible by remember { mutableStateOf(false) }

    // Дозвіл на сповіщення (Android 13+) для нагадувань пити воду.
    val notificationPermissionLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { granted ->
        viewModel.onWaterReminderChange(granted)
    }

    // Дозвіл на читання календаря — щоб не нагадувати під час зустрічей.
    val calendarPermissionLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { granted ->
        viewModel.onSkipDuringMeetingsChange(granted)
    }

    val savedMessage = stringResource(R.string.profile_saved)
    state.errorRes?.let { res ->
        val message = stringResource(res)
        androidx.compose.runtime.LaunchedEffect(res) {
            snackbarHostState.showSnackbar(message)
            viewModel.errorShown()
        }
    }
    androidx.compose.runtime.LaunchedEffect(state.savedEvent) {
        if (state.savedEvent) {
            snackbarHostState.showSnackbar(savedMessage)
            viewModel.savedEventHandled()
        }
    }

    Scaffold(
        topBar = { TopAppBar(title = { Text(stringResource(R.string.profile_title)) }) },
        snackbarHost = { SnackbarHost(snackbarHostState) }
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .verticalScroll(rememberScrollState())
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp)
        ) {
            // --- Базові поля ---
            Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                NumberField(
                    value = state.age,
                    onValueChange = viewModel::onAgeChange,
                    label = stringResource(R.string.profile_age),
                    modifier = Modifier.weight(1f)
                )
                NumberField(
                    value = state.heightCm,
                    onValueChange = viewModel::onHeightChange,
                    label = stringResource(R.string.profile_height),
                    modifier = Modifier.weight(1f)
                )
                NumberField(
                    value = state.weightKg,
                    onValueChange = viewModel::onWeightChange,
                    label = stringResource(R.string.profile_weight),
                    modifier = Modifier.weight(1f),
                    decimal = true
                )
            }

            // --- Стать ---
            SectionLabel(stringResource(R.string.profile_sex))
            FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Sex.entries.forEach { sex ->
                    FilterChip(
                        selected = state.sex == sex,
                        onClick = { viewModel.onSexChange(sex) },
                        label = { Text(sexLabel(sex)) }
                    )
                }
            }

            // --- Активність ---
            SectionLabel(stringResource(R.string.profile_activity))
            FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                ActivityLevel.entries.forEach { level ->
                    FilterChip(
                        selected = state.activityLevel == level,
                        onClick = { viewModel.onActivityChange(level) },
                        label = { Text(activityLabel(level)) }
                    )
                }
            }

            // --- Ціль ---
            SectionLabel(stringResource(R.string.profile_goal))
            FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Goal.entries.forEach { goal ->
                    FilterChip(
                        selected = state.goal == goal,
                        onClick = { viewModel.onGoalChange(goal) },
                        label = { Text(goalLabel(goal)) }
                    )
                }
            }

            // --- Розрахунки ---
            state.targets?.let { targets ->
                Card(
                    modifier = Modifier.fillMaxWidth(),
                    shape = MaterialTheme.shapes.large,
                    colors = CardDefaults.cardColors(
                        containerColor = MaterialTheme.colorScheme.primaryContainer
                    )
                ) {
                    Column(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(20.dp),
                        verticalArrangement = Arrangement.spacedBy(8.dp)
                    ) {
                        StatRow(stringResource(R.string.profile_bmr), targets.bmr)
                        StatRow(stringResource(R.string.profile_tdee), targets.tdee)
                        HorizontalDivider()
                        Text(
                            text = stringResource(R.string.profile_target),
                            style = MaterialTheme.typography.titleMedium,
                            color = MaterialTheme.colorScheme.onPrimaryContainer
                        )
                        Text(
                            text = stringResource(
                                R.string.profile_kcal_per_day,
                                targets.targetKcal
                            ),
                            style = MaterialTheme.typography.headlineSmall,
                            color = MaterialTheme.colorScheme.onPrimaryContainer
                        )
                    }
                }
            }

            Button(
                onClick = viewModel::save,
                modifier = Modifier
                    .fillMaxWidth()
                    .heightIn(min = 52.dp)
            ) {
                Text(
                    text = stringResource(R.string.profile_save),
                    style = MaterialTheme.typography.titleMedium
                )
            }

            HorizontalDivider()

            // --- Тема ---
            SectionLabel(stringResource(R.string.profile_theme))
            FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                ThemeMode.entries.forEach { mode ->
                    FilterChip(
                        selected = state.themeMode == mode,
                        onClick = { viewModel.onThemeModeChange(mode) },
                        label = { Text(themeLabel(mode)) }
                    )
                }
            }
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text(
                    text = stringResource(R.string.profile_dynamic_color),
                    style = MaterialTheme.typography.bodyLarge,
                    color = MaterialTheme.colorScheme.onSurface
                )
                Switch(
                    checked = state.dynamicColor,
                    onCheckedChange = viewModel::onDynamicColorChange
                )
            }

            HorizontalDivider()

            // --- AI-ключ ---
            SectionLabel(stringResource(R.string.profile_api_section))
            OutlinedTextField(
                value = state.apiKey,
                onValueChange = viewModel::onApiKeyChange,
                label = { Text(stringResource(R.string.profile_api_key)) },
                placeholder = { Text(stringResource(R.string.profile_api_key_hint)) },
                singleLine = true,
                visualTransformation = if (apiKeyVisible) VisualTransformation.None
                else PasswordVisualTransformation(),
                trailingIcon = {
                    IconButton(onClick = { apiKeyVisible = !apiKeyVisible }) {
                        Icon(
                            imageVector = if (apiKeyVisible) Icons.Filled.VisibilityOff
                            else Icons.Filled.Visibility,
                            contentDescription = stringResource(
                                if (apiKeyVisible) R.string.profile_api_key_hide
                                else R.string.profile_api_key_show
                            )
                        )
                    }
                },
                modifier = Modifier.fillMaxWidth()
            )
            Text(
                text = stringResource(R.string.profile_api_key_help),
                style = MaterialTheme.typography.labelMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )

            HorizontalDivider()

            // --- Нагадування пити воду ---
            SectionLabel(stringResource(R.string.profile_water_section))
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text(
                    text = stringResource(R.string.profile_water_enable),
                    style = MaterialTheme.typography.bodyLarge,
                    color = MaterialTheme.colorScheme.onSurface
                )
                Switch(
                    checked = state.waterReminderEnabled,
                    onCheckedChange = { enabled ->
                        if (enabled && Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                            // Спершу питаємо дозвіл; результат увімкне/вимкне нагадування.
                            notificationPermissionLauncher.launch(
                                Manifest.permission.POST_NOTIFICATIONS
                            )
                        } else {
                            viewModel.onWaterReminderChange(enabled)
                        }
                    }
                )
            }
            if (state.waterReminderEnabled) {
                Text(
                    text = stringResource(R.string.profile_water_interval),
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
                FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    listOf(1, 2, 3, 4).forEach { hours ->
                        FilterChip(
                            selected = state.waterIntervalHours == hours,
                            onClick = { viewModel.onWaterIntervalChange(hours) },
                            label = { Text(stringResource(R.string.profile_water_every_hours, hours)) }
                        )
                    }
                }

                // Інтеграція з календарем: не нагадувати під час зустрічей.
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text(
                        text = stringResource(R.string.profile_water_skip_meetings),
                        style = MaterialTheme.typography.bodyLarge,
                        color = MaterialTheme.colorScheme.onSurface,
                        modifier = Modifier.weight(1f)
                    )
                    Switch(
                        checked = state.skipDuringMeetings,
                        onCheckedChange = { enabled ->
                            val granted = ContextCompat.checkSelfPermission(
                                context, Manifest.permission.READ_CALENDAR
                            ) == PackageManager.PERMISSION_GRANTED
                            if (enabled && !granted) {
                                calendarPermissionLauncher.launch(Manifest.permission.READ_CALENDAR)
                            } else {
                                viewModel.onSkipDuringMeetingsChange(enabled)
                            }
                        }
                    )
                }
                Text(
                    text = stringResource(R.string.profile_water_skip_meetings_help),
                    style = MaterialTheme.typography.labelMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }
        }
    }
}

@Composable
private fun SectionLabel(text: String) {
    Text(
        text = text,
        style = MaterialTheme.typography.titleMedium,
        color = MaterialTheme.colorScheme.onSurface
    )
}

@Composable
private fun StatRow(label: String, value: Int) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween
    ) {
        Text(
            text = label,
            style = MaterialTheme.typography.bodyLarge,
            color = MaterialTheme.colorScheme.onPrimaryContainer
        )
        Text(
            text = "$value ккал",
            style = MaterialTheme.typography.bodyLarge,
            color = MaterialTheme.colorScheme.onPrimaryContainer
        )
    }
}

@Composable
private fun NumberField(
    value: String,
    onValueChange: (String) -> Unit,
    label: String,
    modifier: Modifier = Modifier,
    decimal: Boolean = false
) {
    OutlinedTextField(
        value = value,
        onValueChange = onValueChange,
        label = { Text(label) },
        singleLine = true,
        keyboardOptions = KeyboardOptions(
            keyboardType = if (decimal) KeyboardType.Decimal else KeyboardType.Number
        ),
        modifier = modifier
    )
}

@Composable
private fun sexLabel(sex: Sex): String = when (sex) {
    Sex.MALE -> stringResource(R.string.profile_sex_male)
    Sex.FEMALE -> stringResource(R.string.profile_sex_female)
}

@Composable
private fun activityLabel(level: ActivityLevel): String = when (level) {
    ActivityLevel.SEDENTARY -> stringResource(R.string.profile_activity_sedentary)
    ActivityLevel.LIGHT -> stringResource(R.string.profile_activity_light)
    ActivityLevel.MODERATE -> stringResource(R.string.profile_activity_moderate)
    ActivityLevel.HIGH -> stringResource(R.string.profile_activity_high)
    ActivityLevel.VERY_HIGH -> stringResource(R.string.profile_activity_very_high)
}

@Composable
private fun goalLabel(goal: Goal): String = when (goal) {
    Goal.MAINTAIN -> stringResource(R.string.profile_goal_maintain)
    Goal.LOSE -> stringResource(R.string.profile_goal_lose)
    Goal.GAIN -> stringResource(R.string.profile_goal_gain)
}

@Composable
private fun themeLabel(mode: ThemeMode): String = when (mode) {
    ThemeMode.SYSTEM -> stringResource(R.string.profile_theme_system)
    ThemeMode.LIGHT -> stringResource(R.string.profile_theme_light)
    ThemeMode.DARK -> stringResource(R.string.profile_theme_dark)
}
