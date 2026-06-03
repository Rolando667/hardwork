package com.calorieai.app.ui.diary

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
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
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.SnackbarResult
import androidx.compose.material3.Text
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
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.calorieai.app.R
import com.calorieai.app.domain.model.FoodEntry
import com.calorieai.app.ui.components.CalorieProgressRing
import com.calorieai.app.ui.components.EditEntryDialog
import com.calorieai.app.ui.components.EmptyState
import com.calorieai.app.ui.components.FoodEntryCard
import com.calorieai.app.ui.components.MacroBars
import com.calorieai.app.util.DateUtils
import kotlinx.coroutines.launch
import java.time.LocalDate

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun DiaryScreen(
    viewModel: DiaryViewModel = hiltViewModel()
) {
    val state by viewModel.uiState.collectAsStateWithLifecycle()
    val snackbarHostState = remember { SnackbarHostState() }
    val scope = rememberCoroutineScope()
    var editing by remember { mutableStateOf<FoodEntry?>(null) }

    val deletedMessage = stringResource(R.string.entry_deleted)
    val undoLabel = stringResource(R.string.entry_undo)

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

            item {
                SummaryCard(state = state)
            }

            if (state.entries.isEmpty()) {
                item {
                    EmptyState(
                        icon = Icons.AutoMirrored.Filled.MenuBook,
                        title = stringResource(R.string.diary_empty_title),
                        subtitle = stringResource(R.string.diary_empty_subtitle)
                    )
                }
            } else {
                items(state.entries, key = { it.id }) { entry ->
                    AnimatedVisibility(visible = true) {
                        FoodEntryCard(
                            entry = entry,
                            onEdit = { editing = entry },
                            onDelete = {
                                viewModel.deleteEntry(entry)
                                scope.launch {
                                    val result = snackbarHostState.showSnackbar(
                                        message = deletedMessage,
                                        actionLabel = undoLabel
                                    )
                                    if (result == SnackbarResult.ActionPerformed) {
                                        viewModel.undoDelete()
                                    }
                                }
                            },
                            modifier = Modifier.animateItem()
                        )
                    }
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
            Icon(
                Icons.Filled.ChevronLeft,
                contentDescription = stringResource(R.string.diary_prev_day)
            )
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
            Icon(
                Icons.Filled.ChevronRight,
                contentDescription = stringResource(R.string.diary_next_day)
            )
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
                CalorieProgressRing(
                    consumed = state.consumedKcal,
                    target = targets.targetKcal
                )
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
