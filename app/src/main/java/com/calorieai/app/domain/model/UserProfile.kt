package com.calorieai.app.domain.model

/**
 * Профіль користувача. [isComplete] — чи достатньо даних для розрахунку норми.
 */
data class UserProfile(
    val age: Int = 0,
    val sex: Sex = Sex.MALE,
    val heightCm: Int = 0,
    val weightKg: Double = 0.0,
    val activityLevel: ActivityLevel = ActivityLevel.SEDENTARY,
    val goal: Goal = Goal.MAINTAIN
) {
    val isComplete: Boolean
        get() = age in 1..120 && heightCm in 50..272 && weightKg in 20.0..400.0
}
