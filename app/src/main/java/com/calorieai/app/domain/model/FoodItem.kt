package com.calorieai.app.domain.model

/**
 * Одна позиція їжі — результат AI-аналізу або ручного вводу.
 * Використовується як у мережевому шарі (через DTO), так і в UI.
 */
data class FoodItem(
    val name: String,
    val grams: Int,
    val kcal: Int,
    val protein: Double,
    val fat: Double,
    val carbs: Double
)
