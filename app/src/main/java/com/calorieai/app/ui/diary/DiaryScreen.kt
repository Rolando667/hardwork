package com.calorieai.app.ui.diary

import androidx.compose.animation.animateContentSize
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.MenuBook
import androidx.compose.material.icons.filled.ChevronLeft
import androidx.compose.material.icons.filled.ChevronRight
import androidx.compose.material.icons.filled.DeleteOutline
import androidx.compose.material.icons.filled.EditNote
import androidx.compose.material.icons.filled.ExpandLess
import androidx.compose.material.icons.filled.ExpandMore
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.SnackbarResult
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.calorieai.app.R
import com.calorieai.app.domain.model.FoodEntry
import com.calorieai.app.domain.model.MealType
import com.calorieai.app.ui.components.CalorieProgressRing
import com.calorieai.app.ui.components.EditEntryDialog
import com.calorieai.app.ui.components.EmptyState
import com.calorieai.app.ui.components.MacroBars
import com.calorieai.app.ui.components.mealTypeLabel
import com.calorieai.app.util.DateUtils
import kotlinx.coroutines.launch
import java.time.Instant
import java.time.LocalDate
import java.time.ZoneId
import java.time.format.DateTimeFormatter

@OptIn(ExperimentalMaterial3Api::class, ExperimentalLayoutApi::class)
@Composable
fun DiaryScreen(
    viewModel: DiaryViewModel = hiltViewModel()
) {
    val state by viewModel.uiState.collectAsStateWithLifecycle()
    val snackbarHostState = remember { SnackbarHostState() }
    val scope = rememberCoroutineScope()
    var editing by remember { mutableStateOf<FoodEntry?>(null) }
    var expandedIds by remember { mutableStateOf(setOf<String>()) }
    // Дія видалення, що очікує підтвердження в діалозі.
    var pendingDelete by remember { mutableStateOf<(() -> Unit)?>(null) }

    val deletedMessage = stringResource(R.string.entry_deleted)
    val undoLabel = stringResource(R.string.entry_undo)

    fun confirmDelete(action: () -> Unit) {
        action()
        scope.launch {
            val result = snackbarHostState.showSnackbar(
                message = deletedMessage,
                actionLabel = undoLabel
            )
            if (result == SnackbarResult.ActionPerformed) viewModel.undoDelete()
        }
    }

    Scaffold(
        topBar = { TopAppBar(title = { Text(stringResource(R.string.diary_title)) }) },
        snackbarHost = { SnackbarHost(snackbarHostState) }
    ) { padding ->
        LazyColumn(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding),
            contentPadding = PaddingValues(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            item {
                DateSelector(
                    date = state.date,
                    onPrev = viewModel::previousDay,
                    onNext = viewModel::nextDay
                )
            }

            item { SummaryCard(state = state) }

            if (state.hasAnyEntries) {
                item {
                    MealFilterRow(
                        selected = state.filter,
                        onSelect = viewModel::setFilter
                    )
                }
            }

            if (!state.hasAnyEntries) {
                item {
                    EmptyState(
                        icon = Icons.AutoMirrored.Filled.MenuBook,
                        title = stringResource(R.string.diary_empty_title),
                        subtitle = stringResource(R.string.diary_empty_subtitle)
                    )
                }
            } else {
                items(state.meals, key = { it.groupId }) { meal ->
                    MealCard(
                        meal = meal,
                        expanded = meal.groupId in expandedIds,
                        onToggle = {
                            expandedIds = if (meal.groupId in expandedIds) {
                                expandedIds - meal.groupId
                            } else {
                                expandedIds + meal.groupId
                            }
                        },
                        onDeleteMeal = {
                            pendingDelete = { confirmDelete { viewModel.deleteMeal(meal) } }
                        },
                        onEditItem = { editing = it },
                        onDeleteItem = { item ->
                            pendingDelete = { confirmDelete { viewModel.deleteEntry(item) } }
                        },
                        modifier = Modifier.animateItem()
                    )
                }
            }
        }
    }

    editing?.let { entry ->
        EditEntryDialog(
            entry = entry,
            onSave = {
                viewModel.updateEntry(it)
                editing = null
            },
            onDismiss = { editing = null }
        )
    }

    pendingDelete?.let { action ->
        AlertDialog(
            onDismissRequest = { pendingDelete = null },
            title = { Text(stringResource(R.string.delete_confirm_title)) },
            text = { Text(stringResource(R.string.delete_confirm_message)) },
            confirmButton = {
                TextButton(onClick = {
                    action()
                    pendingDelete = null
                }) {
                    Text(
                        text = stringResource(R.string.entry_delete),
                        color = MaterialTheme.colorScheme.error
                    )
                }
            },
            dismissButton = {
                TextButton(onClick = { pendingDelete = null }) {
                    Text(stringResource(R.string.entry_cancel))
                }
            }
        )
    }
}

@OptIn(ExperimentalLayoutApi::class, ExperimentalMaterial3Api::class)
@Composable
private fun MealFilterRow(
    selected: MealType?,
    onSelect: (MealType?) -> Unit
) {
    FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        FilterChip(
            selected = selected == null,
            onClick = { onSelect(null) },
            label = { Text(stringResource(R.string.diary_filter_all)) }
        )
        MealType.entries.forEach { type ->
            FilterChip(
                selected = selected == type,
                onClick = { onSelect(type) },
                label = { Text(mealTypeLabel(type)) }
            )
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun MealCard(
    meal: DiaryMeal,
    expanded: Boolean,
    onToggle: () -> Unit,
    onDeleteMeal: () -> Unit,
    onEditItem: (FoodEntry) -> Unit,
    onDeleteItem: (FoodEntry) -> Unit,
    modifier: Modifier = Modifier
) {
    Card(
        onClick = onToggle,
        modifier = modifier
            .fillMaxWidth()
            .animateContentSize(),
        shape = MaterialTheme.shapes.medium,
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.35f)
        ),
        elevation = CardDefaults.cardElevation(defaultElevation = 1.dp)
    ) {
        Column(modifier = Modifier.padding(start = 16.dp, top = 12.dp, bottom = 12.dp, end = 4.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(modifier = Modifier.weight(1f)) {
                    val time = mealTime(meal.createdAt)
                    Text(
                        text = mealTypeLabel(meal.mealType) + if (time != null) "  ·  $time" else "",
                        style = MaterialTheme.typography.titleMedium,
                        color = MaterialTheme.colorScheme.primary
                    )
                    Text(
                        text = "${meal.totalKcal} ${stringResource(R.string.diary_kcal)} · " +
                            "Б ${fmt(meal.totalProtein)} · Ж ${fmt(meal.totalFat)} · " +
                            "В ${fmt(meal.totalCarbs)}",
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurface
                    )
                    if (!expanded) {
                        val subtitle = if (meal.items.size == 1) {
                            meal.items.first().name
                        } else {
                            stringResource(R.string.diary_meal_components, meal.items.size)
                        }
                        Text(
                            text = subtitle,
                            style = MaterialTheme.typography.labelMedium,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                    }
                }
                IconButton(onClick = onDeleteMeal) {
                    Icon(
                        Icons.Filled.DeleteOutline,
                        contentDescription = stringResource(R.string.entry_delete),
                        tint = MaterialTheme.colorScheme.error
                    )
                }
                Icon(
                    imageVector = if (expanded) Icons.Filled.ExpandLess else Icons.Filled.ExpandMore,
                    contentDescription = null,
                    tint = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }

            if (expanded) {
                HorizontalDivider(modifier = Modifier.padding(vertical = 8.dp, horizontal = 0.dp))
                meal.items.forEach { item ->
                    ComponentRow(
                        item = item,
                        onEdit = { onEditItem(item) },
                        onDelete = { onDeleteItem(item) }
                    )
                }
            }
        }
    }
}

@Composable
private fun ComponentRow(
    item: FoodEntry,
    onEdit: () -> Unit,
    onDelete: () -> Unit
) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Column(modifier = Modifier.weight(1f)) {
            Text(
                text = item.name,
                style = MaterialTheme.typography.bodyLarge,
                color = MaterialTheme.colorScheme.onSurface
            )
            Text(
                text = "${item.grams} ${stringResource(R.string.diary_grams_short)} · " +
                    "${item.kcal} ${stringResource(R.string.diary_kcal)} · " +
                    "Б ${fmt(item.protein)} · Ж ${fmt(item.fat)} · В ${fmt(item.carbs)}",
                style = MaterialTheme.typography.labelMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
        }
        IconButton(onClick = onEdit) {
            Icon(
                Icons.Filled.EditNote,
                contentDescription = stringResource(R.string.entry_edit),
                tint = MaterialTheme.colorScheme.primary
            )
        }
        IconButton(onClick = onDelete) {
            Icon(
                Icons.Filled.DeleteOutline,
                contentDescription = stringResource(R.string.entry_delete),
                tint = MaterialTheme.colorScheme.error
            )
        }
    }
}

@Composable
private fun DateSelector(
    date: LocalDate,
    onPrev: () -> Unit,
    onNext: () -> Unit
) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically
    ) {
        IconButton(onClick = onPrev) {
            Icon(Icons.Filled.ChevronLeft, contentDescription = stringResource(R.string.diary_prev_day))
        }
        Column(horizontalAlignment = Alignment.CenterHorizontally) {
            Text(
                text = dateLabel(date),
                style = MaterialTheme.typography.titleMedium,
                color = MaterialTheme.colorScheme.onSurface
            )
            Text(
                text = DateUtils.formatWeekday(date),
                style = MaterialTheme.typography.labelMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
        }
        IconButton(onClick = onNext) {
            Icon(Icons.Filled.ChevronRight, contentDescription = stringResource(R.string.diary_next_day))
        }
    }
}

@Composable
private fun dateLabel(date: LocalDate): String = when (date) {
    LocalDate.now() -> stringResource(R.string.diary_today)
    LocalDate.now().minusDays(1) -> stringResource(R.string.diary_yesterday)
    else -> DateUtils.formatFull(date)
}

@Composable
private fun SummaryCard(state: DiaryUiState) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        shape = MaterialTheme.shapes.large,
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.3f)
        ),
        elevation = CardDefaults.cardElevation(defaultElevation = 2.dp)
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(20.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(20.dp)
        ) {
            val targets = state.targets
            if (targets == null) {
                Box(modifier = Modifier.padding(16.dp)) {
                    Text(
                        text = stringResource(R.string.diary_set_profile_hint),
                        style = MaterialTheme.typography.bodyLarge,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
                CalorieProgressRing(consumed = state.consumedKcal, target = 0)
            } else {
                CalorieProgressRing(consumed = state.consumedKcal, target = targets.targetKcal)
                MacroBars(
                    proteinCurrent = state.consumedProtein,
                    proteinTarget = targets.proteinG,
                    fatCurrent = state.consumedFat,
                    fatTarget = targets.fatG,
                    carbsCurrent = state.consumedCarbs,
                    carbsTarget = targets.carbsG
                )
            }
        }
    }
}

private val timeFormatter = DateTimeFormatter.ofPattern("HH:mm")

/** Час прийому з epoch millis; null для старих записів без коректного часу. */
private fun mealTime(createdAt: Long): String? {
    if (createdAt < 1_000_000_000_000L) return null
    return Instant.ofEpochMilli(createdAt)
        .atZone(ZoneId.systemDefault())
        .toLocalTime()
        .format(timeFormatter)
}

private fun fmt(value: Double): String =
    if (value % 1.0 == 0.0) "${value.toInt()}г" else String.format("%.1fг", value)
