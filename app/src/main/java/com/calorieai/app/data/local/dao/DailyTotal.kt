package com.calorieai.app.data.local.dao

import java.time.LocalDate

/** Агрегат калорій і макросів за один день (результат GROUP BY у запиті). */
data class DailyTotal(
    val date: LocalDate,
    val kcal: Int,
    val protein: Double,
    val fat: Double,
    val carbs: Double
)
