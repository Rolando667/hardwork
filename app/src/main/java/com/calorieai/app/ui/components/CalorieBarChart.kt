package com.calorieai.app.ui.components

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.drawText
import androidx.compose.ui.text.rememberTextMeasurer
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

/** Один стовпчик графіка: підпис під віссю та значення. */
data class BarEntry(val label: String, val value: Int)

/** Стовпчиковий графік калорій за днями з пунктирною лінією денної норми. */
@Composable
fun CalorieBarChart(
    entries: List<BarEntry>,
    targetKcal: Int?,
    modifier: Modifier = Modifier
) {
    if (entries.isEmpty()) return

    val barColor = MaterialTheme.colorScheme.primary
    val overColor = MaterialTheme.colorScheme.error
    val targetColor = MaterialTheme.colorScheme.tertiary
    val axisColor = MaterialTheme.colorScheme.outline
    val labelColor = MaterialTheme.colorScheme.onSurfaceVariant
    val textMeasurer = rememberTextMeasurer()
    val density = LocalDensity.current

    val maxValue = maxOf(entries.maxOf { it.value }, targetKcal ?: 0, 1)

    Box(
        modifier = modifier
            .fillMaxWidth()
            .height(220.dp)
            .padding(8.dp)
    ) {
        Canvas(modifier = Modifier.fillMaxWidth().height(220.dp)) {
            val labelHeight = with(density) { 16.dp.toPx() }
            val chartHeight = size.height - labelHeight
            val barCount = entries.size
            val slot = size.width / barCount
            val barWidth = slot * 0.55f

            drawLine(
                color = axisColor,
                start = Offset(0f, chartHeight),
                end = Offset(size.width, chartHeight),
                strokeWidth = 2f
            )

            targetKcal?.let { target ->
                val y = chartHeight - (target.toFloat() / maxValue) * chartHeight
                drawLine(
                    color = targetColor,
                    start = Offset(0f, y),
                    end = Offset(size.width, y),
                    strokeWidth = 3f,
                    pathEffect = PathEffect.dashPathEffect(floatArrayOf(14f, 10f))
                )
            }

            entries.forEachIndexed { index, entry ->
                val barHeight =
                    if (entry.value > 0) (entry.value.toFloat() / maxValue) * chartHeight else 0f
                val left = index * slot + (slot - barWidth) / 2
                val top = chartHeight - barHeight
                val color =
                    if (targetKcal != null && entry.value > targetKcal) overColor else barColor

                drawRoundedBar(color, left, top, barWidth, barHeight)

                val labelLayout = textMeasurer.measure(
                    entry.label,
                    style = TextStyle(fontSize = 9.sp, color = labelColor)
                )
                drawText(
                    textLayoutResult = labelLayout,
                    topLeft = Offset(
                        left + barWidth / 2 - labelLayout.size.width / 2,
                        chartHeight + 2f
                    )
                )
            }
        }
    }
}

private fun DrawScope.drawRoundedBar(
    color: Color,
    left: Float,
    top: Float,
    width: Float,
    height: Float
) {
    if (height <= 0f) return
    drawRoundRect(
        color = color,
        topLeft = Offset(left, top),
        size = Size(width, height),
        cornerRadius = CornerRadius(width / 3, width / 3)
    )
}
