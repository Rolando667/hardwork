package com.calorieai.app.ui.components

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.drawText
import androidx.compose.ui.text.rememberTextMeasurer
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.calorieai.app.domain.model.WeightPoint
import java.time.format.DateTimeFormatter
import kotlin.math.max

/** Лінійний графік динаміки ваги з точками та підписами країв. */
@Composable
fun WeightLineChart(
    points: List<WeightPoint>,
    modifier: Modifier = Modifier
) {
    if (points.isEmpty()) return

    val lineColor = MaterialTheme.colorScheme.primary
    val pointColor = MaterialTheme.colorScheme.secondary
    val gridColor = MaterialTheme.colorScheme.outline
    val labelColor = MaterialTheme.colorScheme.onSurfaceVariant
    val textMeasurer = rememberTextMeasurer()

    val values = points.map { it.weightKg }
    val minW = values.min()
    val maxW = values.max()
    // Невеликий відступ зверху/знизу, щоб лінія не торкалась країв.
    val pad = max((maxW - minW) * 0.15, 0.5)
    val lo = minW - pad
    val hi = maxW + pad
    val span = (hi - lo).takeIf { it > 0.0 } ?: 1.0

    Box(
        modifier = modifier
            .fillMaxWidth()
            .height(200.dp)
            .padding(8.dp)
    ) {
        Canvas(modifier = Modifier.fillMaxWidth().height(200.dp)) {
            val labelSpace = 18f
            val chartHeight = size.height - labelSpace
            val chartWidth = size.width
            val stepX = if (points.size > 1) chartWidth / (points.size - 1) else 0f

            fun yFor(w: Double): Float =
                (chartHeight - ((w - lo) / span * chartHeight)).toFloat()

            // Горизонтальні орієнтири (min / max)
            drawLine(gridColor, Offset(0f, yFor(maxW)), Offset(chartWidth, yFor(maxW)), 1.5f)
            drawLine(gridColor, Offset(0f, yFor(minW)), Offset(chartWidth, yFor(minW)), 1.5f)

            // Лінія
            val path = Path()
            points.forEachIndexed { index, point ->
                val x = if (points.size > 1) index * stepX else chartWidth / 2
                val y = yFor(point.weightKg)
                if (index == 0) path.moveTo(x, y) else path.lineTo(x, y)
            }
            drawPath(path, color = lineColor, style = Stroke(width = 5f))

            // Точки
            points.forEachIndexed { index, point ->
                val x = if (points.size > 1) index * stepX else chartWidth / 2
                drawCircle(pointColor, radius = 7f, center = Offset(x, yFor(point.weightKg)))
            }

            // Підписи мін/макс ваги
            val maxLabel = textMeasurer.measure(
                "${trim(maxW)} кг",
                style = TextStyle(fontSize = 10.sp, color = labelColor)
            )
            drawText(maxLabel, topLeft = Offset(4f, yFor(maxW) + 2f))
            val minLabel = textMeasurer.measure(
                "${trim(minW)} кг",
                style = TextStyle(fontSize = 10.sp, color = labelColor)
            )
            drawText(minLabel, topLeft = Offset(4f, yFor(minW) - minLabel.size.height - 2f))

            // Підписи крайніх дат
            val first = textMeasurer.measure(
                dateFmt.format(points.first().date),
                style = TextStyle(fontSize = 9.sp, color = labelColor)
            )
            drawText(first, topLeft = Offset(0f, chartHeight + 2f))
            if (points.size > 1) {
                val last = textMeasurer.measure(
                    dateFmt.format(points.last().date),
                    style = TextStyle(fontSize = 9.sp, color = labelColor)
                )
                drawText(
                    last,
                    topLeft = Offset(chartWidth - last.size.width.toFloat(), chartHeight + 2f)
                )
            }
        }
    }
}

private val dateFmt = DateTimeFormatter.ofPattern("dd.MM")

private fun trim(value: Double): String =
    if (value % 1.0 == 0.0) value.toInt().toString() else String.format("%.1f", value)
