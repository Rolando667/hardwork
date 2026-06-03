package com.calorieai.app.ui.add

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.DeleteOutline
import androidx.compose.material.icons.filled.EditNote
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import com.calorieai.app.R
import com.calorieai.app.domain.model.FoodEntry
import com.calorieai.app.domain.model.FoodItem
import com.calorieai.app.ui.components.EditEntryDialog
import java.time.LocalDate

/** Список розпізнаних позицій з можливістю редагувати/видаляти та зберегти всі. */
@Composable
fun ResultsSection(
    state: AddUiState,
    onEdit: (Int, FoodItem) -> Unit,
    onRemove: (Int) -> Unit,
    onSaveAll: () -> Unit,
    onClear: () -> Unit
) {
    var editingIndex by remember { mutableStateOf<Int?>(null) }

    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Text(
            text = stringResource(R.string.add_results_title),
            style = MaterialTheme.typography.titleLarge,
            color = MaterialTheme.colorScheme.onSurface
        )

        state.results.forEachIndexed { index, item ->
            ResultRow(
                item = item,
                onEdit = { editingIndex = index },
                onRemove = { onRemove(index) }
            )
        }

        state.note?.takeIf { it.isNotBlank() }?.let { note ->
            Text(
                text = note,
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
        }

        Text(
            text = stringResource(R.string.add_total, state.totalKcal),
            style = MaterialTheme.typography.titleMedium,
            color = MaterialTheme.colorScheme.primary
        )

        Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            OutlinedButton(
                onClick = onClear,
                modifier = Modifier.weight(1f).heightIn(min = 52.dp)
            ) {
                Text(stringResource(R.string.add_clear))
            }
            Button(
                onClick = onSaveAll,
                modifier = Modifier.weight(1f).heightIn(min = 52.dp)
            ) {
                Text(stringResource(R.string.add_save_all))
            }
        }
    }

    editingIndex?.let { index ->
        val item = state.results[index]
        EditEntryDialog(
            entry = item.toEntry(),
            onSave = { updated ->
                onEdit(index, updated.toItem())
                editingIndex = null
            },
            onDismiss = { editingIndex = null }
        )
    }
}

@Composable
private fun ResultRow(
    item: FoodItem,
    onEdit: () -> Unit,
    onRemove: () -> Unit
) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        shape = MaterialTheme.shapes.medium,
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.secondaryContainer.copy(alpha = 0.35f)
        )
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(start = 16.dp, top = 12.dp, bottom = 12.dp, end = 4.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Column(modifier = Modifier.weight(1f)) {
                Text(
                    text = item.name,
                    style = MaterialTheme.typography.titleMedium,
                    color = MaterialTheme.colorScheme.onSurface
                )
                Text(
                    text = "${item.grams} г · ${item.kcal} ккал",
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
                Text(
                    text = "Б ${fmt(item.protein)} · Ж ${fmt(item.fat)} · В ${fmt(item.carbs)}",
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
            IconButton(onClick = onRemove) {
                Icon(
                    Icons.Filled.DeleteOutline,
                    contentDescription = stringResource(R.string.entry_delete),
                    tint = MaterialTheme.colorScheme.error
                )
            }
        }
    }
}

private fun fmt(value: Double): String =
    if (value % 1.0 == 0.0) "${value.toInt()}г" else String.format("%.1fг", value)

private fun FoodItem.toEntry(): FoodEntry = FoodEntry(
    date = LocalDate.now(),
    name = name,
    grams = grams,
    kcal = kcal,
    protein = protein,
    fat = fat,
    carbs = carbs
)

private fun FoodEntry.toItem(): FoodItem = FoodItem(
    name = name,
    grams = grams,
    kcal = kcal,
    protein = protein,
    fat = fat,
    carbs = carbs
)
