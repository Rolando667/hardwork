package com.calorieai.app.domain.model

/**
 * Ціль користувача. [calorieOffset] додається до TDEE, щоб отримати денну норму:
 * підтримка 0, схуднення −500, набір +500 ккал.
 */
enum class Goal(val calorieOffset: Int) {
    MAINTAIN(0),
    LOSE(-500),
    GAIN(500)
}
