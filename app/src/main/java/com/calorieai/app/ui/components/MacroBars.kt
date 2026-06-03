package com.calorieai.app.ui.components

import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import com.calorieai.app.ui.theme.CarbsColor
import com.calorieai.app.ui.theme.FatColor
import com.calorieai.app.ui.theme.ProteinColor

/** Три смужки прогресу Б/Ж/В із поточним значенням та ціллю (у грамах). */
@Composable
fun MacroBars(
    proteinCurrent: Int,
    proteinTarget: Int,
    fatCurrent: Int,
    fatTarget: Int,
    carbsCurrent: Int,
    carbsTarget: Int,
    modifier: Modifier = Modifier
) {
    Column(
        modifier = modifier.fillMaxWidth(),
        verticalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        MacroBar("Білки", proteinCurrent, proteinTarget, ProteinColor)
        MacroBar("Жири", fatCurrent, fatTarget, FatColor)
        MacroBar("Вуглеводи", carbsCurrent, carbsTarget, CarbsColor)
    }
}

@Composable
private fun MacroBar(
    label: String,
    current: Int,
    target: Int,
    color: Color
) {
    val fraction = if (target > 0) (current.toFloat() / target).coerceIn(0f, 1f) else 0f
    val animated by animateFloatAsState(
        targetValue = fraction,
        animationSpec = tween(700),
        label = "macro_$label"
    )

    Column {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween
        ) {
            Text(
                text = label,
                style = MaterialTheme.typography.labelLarge,
                color = MaterialTheme.colorScheme.onSurface
            )
            Text(
                text = "$current / $target г",
                style = MaterialTheme.typography.labelMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
        }
        Spacer(Modifier.height(4.dp))
        // Власна смужка прогресу зі скругленими кутами.
        Box(
            modifier = Modifier
                .fillMaxWidth()
                .height(10.dp)
                .clip(RoundedCornerShape(6.dp))
                .background(MaterialTheme.colorScheme.surfaceVariant)
        ) {
            Box(
                modifier = Modifier
                    .fillMaxHeight()
                    .fillMaxWidth(animated)
                    .clip(RoundedCornerShape(6.dp))
                    .background(color)
            )
        }
    }
}
