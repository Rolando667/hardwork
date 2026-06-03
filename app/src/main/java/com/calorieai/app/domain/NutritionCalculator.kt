package com.calorieai.app.domain

import com.calorieai.app.domain.model.Sex
import com.calorieai.app.domain.model.UserProfile
import kotlin.math.roundToInt

/** Цільові норми по калоріях та макронутрієнтах на день. */
data class NutritionTargets(
    val bmr: Int,
    val tdee: Int,
    val targetKcal: Int,
    val proteinG: Int,
    val fatG: Int,
    val carbsG: Int
)

/**
 * Розрахунки калорійності за формулою Mifflin-St Jeor.
 *
 * BMR (чол) = 10·вага + 6.25·зріст − 5·вік + 5
 * BMR (жін) = 10·вага + 6.25·зріст − 5·вік − 161
 * TDEE = BMR · коефіцієнт активності
 * Денна норма = TDEE + зсув цілі (−500 / 0 / +500)
 *
 * Розподіл макросів-орієнтир: білки 30%, жири 30%, вуглеводи 40% від норми
 * (білки/вуглеводи = 4 ккал/г, жири = 9 ккал/г).
 */
object NutritionCalculator {

    fun bmr(profile: UserProfile): Double {
        val base = 10 * profile.weightKg + 6.25 * profile.heightCm - 5 * profile.age
        return when (profile.sex) {
            Sex.MALE -> base + 5
            Sex.FEMALE -> base - 161
        }
    }

    fun tdee(profile: UserProfile): Double = bmr(profile) * profile.activityLevel.multiplier

    fun targetKcal(profile: UserProfile): Int =
        (tdee(profile) + profile.goal.calorieOffset).roundToInt()

    fun targets(profile: UserProfile): NutritionTargets {
        val bmr = bmr(profile)
        val tdee = bmr * profile.activityLevel.multiplier
        val target = (tdee + profile.goal.calorieOffset).roundToInt()
        return NutritionTargets(
            bmr = bmr.roundToInt(),
            tdee = tdee.roundToInt(),
            targetKcal = target,
            proteinG = (target * 0.30 / 4).roundToInt(),
            fatG = (target * 0.30 / 9).roundToInt(),
            carbsG = (target * 0.40 / 4).roundToInt()
        )
    }
}
