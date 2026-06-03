package com.calorieai.app.domain.model

/**
 * Рівень фізичної активності та відповідний коефіцієнт для розрахунку TDEE
 * (TDEE = BMR × multiplier).
 */
enum class ActivityLevel(val multiplier: Double) {
    SEDENTARY(1.2),
    LIGHT(1.375),
    MODERATE(1.55),
    HIGH(1.725),
    VERY_HIGH(1.9)
}
