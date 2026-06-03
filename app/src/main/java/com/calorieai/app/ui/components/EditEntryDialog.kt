package com.calorieai.app.ui.components

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import com.calorieai.app.R
import com.calorieai.app.domain.model.FoodEntry

/** Діалог редагування/створення запису. Повертає оновлений [FoodEntry] у [onSave]. */
@Composable
fun EditEntryDialog(
    entry: FoodEntry,
    onSave: (FoodEntry) -> Unit,
    onDismiss: () -> Unit
) {
    var name by remember { mutableStateOf(entry.name) }
    var grams by remember { mutableStateOf(entry.grams.toString()) }
    var kcal by remember { mutableStateOf(entry.kcal.toString()) }
    var protein by remember { mutableStateOf(entry.protein.toString()) }
    var fat by remember { mutableStateOf(entry.fat.toString()) }
    var carbs by remember { mutableStateOf(entry.carbs.toString()) }

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(stringResource(R.string.entry_edit)) },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedTextField(
                    value = name,
                    onValueChange = { name = it },
                    label = { Text(stringResource(R.string.entry_name)) },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth()
                )
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    NumberField(
                        value = grams,
                        onValueChange = { grams = it },
                        label = stringResource(R.string.entry_grams),
                        modifier = Modifier.weight(1f)
                    )
                    NumberField(
                        value = kcal,
                        onValueChange = { kcal = it },
                        label = stringResource(R.string.entry_kcal_label),
                        modifier = Modifier.weight(1f)
                    )
                }
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    NumberField(
                        value = protein,
                        onValueChange = { protein = it },
                        label = stringResource(R.string.entry_protein_label),
                        modifier = Modifier.weight(1f)
                    )
                    NumberField(
                        value = fat,
                        onValueChange = { fat = it },
                        label = stringResource(R.string.entry_fat_label),
                        modifier = Modifier.weight(1f)
                    )
                    NumberField(
                        value = carbs,
                        onValueChange = { carbs = it },
                        label = stringResource(R.string.entry_carbs_label),
                        modifier = Modifier.weight(1f)
                    )
                }
            }
        },
        confirmButton = {
            TextButton(
                onClick = {
                    onSave(
                        entry.copy(
                            name = name.trim().ifBlank { entry.name },
                            grams = grams.toIntOrNull() ?: 0,
                            kcal = kcal.toIntOrNull() ?: 0,
                            protein = protein.toDoubleOrNull() ?: 0.0,
                            fat = fat.toDoubleOrNull() ?: 0.0,
                            carbs = carbs.toDoubleOrNull() ?: 0.0
                        )
                    )
                }
            ) { Text(stringResource(R.string.entry_save)) }
        },
        dismissButton = {
            TextButton(onClick = onDismiss) {
                Text(stringResource(R.string.entry_cancel))
            }
        }
    )
}

@Composable
private fun NumberField(
    value: String,
    onValueChange: (String) -> Unit,
    label: String,
    modifier: Modifier = Modifier
) {
    OutlinedTextField(
        value = value,
        onValueChange = onValueChange,
        label = { Text(label) },
        singleLine = true,
        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
        modifier = modifier
    )
}
