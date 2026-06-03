package com.calorieai.app.util

import java.time.LocalDate
import java.time.format.DateTimeFormatter
import java.util.Locale

object DateUtils {
    private val ukLocale = Locale("uk", "UA")
    private val displayFormatter: DateTimeFormatter =
        DateTimeFormatter.ofPattern("d MMMM yyyy", ukLocale)
    private val weekdayFormatter: DateTimeFormatter =
        DateTimeFormatter.ofPattern("EEEE", ukLocale)

    /** «3 червня 2026» з великої літери. */
    fun formatFull(date: LocalDate): String =
        displayFormatter.format(date).replaceFirstChar { it.titlecase(ukLocale) }

    /** День тижня з великої літери. */
    fun formatWeekday(date: LocalDate): String =
        weekdayFormatter.format(date).replaceFirstChar { it.titlecase(ukLocale) }
}
