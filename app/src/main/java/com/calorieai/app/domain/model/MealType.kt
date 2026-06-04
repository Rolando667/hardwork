package com.calorieai.app.domain.model

/** Прийом їжі. [defaultForHour] підбирає тип за поточним часом доби. */
enum class MealType {
    BREAKFAST,
    LUNCH,
    AFTERNOON,
    DINNER,
    SNACK;

    companion object {
        fun defaultForHour(hour: Int): MealType = when (hour) {
            in 5..10 -> BREAKFAST
            in 11..15 -> LUNCH
            in 16..17 -> AFTERNOON
            in 18..23 -> DINNER
            else -> SNACK
        }
    }
}
