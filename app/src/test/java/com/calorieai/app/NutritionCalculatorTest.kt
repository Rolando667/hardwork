package com.calorieai.app

import com.calorieai.app.domain.NutritionCalculator
import com.calorieai.app.domain.model.ActivityLevel
import com.calorieai.app.domain.model.Goal
import com.calorieai.app.domain.model.Sex
import com.calorieai.app.domain.model.UserProfile
import org.junit.Assert.assertEquals
import org.junit.Test

class NutritionCalculatorTest {

    @Test
    fun `bmr and tdee for male sedentary maintain`() {
        val profile = UserProfile(
            age = 30,
            sex = Sex.MALE,
            heightCm = 180,
            weightKg = 80.0,
            activityLevel = ActivityLevel.SEDENTARY,
            goal = Goal.MAINTAIN
        )
        // BMR = 10*80 + 6.25*180 - 5*30 + 5 = 1780
        assertEquals(1780, NutritionCalculator.bmr(profile).toInt())
        // TDEE = 1780 * 1.2 = 2136
        assertEquals(2136, NutritionCalculator.targets(profile).tdee)
        // maintain offset = 0
        assertEquals(2136, NutritionCalculator.targetKcal(profile))
    }

    @Test
    fun `female lose goal applies minus 500`() {
        val profile = UserProfile(
            age = 25,
            sex = Sex.FEMALE,
            heightCm = 165,
            weightKg = 60.0,
            activityLevel = ActivityLevel.MODERATE,
            goal = Goal.LOSE
        )
        // BMR = 600 + 1031.25 - 125 - 161 = 1345.25
        val tdee = 1345.25 * 1.55 // = 2085.14
        val expected = (tdee - 500).toInt()
        assertEquals(expected, NutritionCalculator.targetKcal(profile))
    }

    @Test
    fun `gain goal adds 500`() {
        val profile = UserProfile(
            age = 40,
            sex = Sex.MALE,
            heightCm = 175,
            weightKg = 70.0,
            activityLevel = ActivityLevel.HIGH,
            goal = Goal.GAIN
        )
        val maintain = NutritionCalculator.targets(profile).tdee
        assertEquals(maintain + 500, NutritionCalculator.targetKcal(profile))
    }

    @Test
    fun `macro split sums roughly to target calories`() {
        val profile = UserProfile(
            age = 30,
            sex = Sex.MALE,
            heightCm = 180,
            weightKg = 80.0,
            activityLevel = ActivityLevel.SEDENTARY,
            goal = Goal.MAINTAIN
        )
        val t = NutritionCalculator.targets(profile)
        val kcalFromMacros = t.proteinG * 4 + t.carbsG * 4 + t.fatG * 9
        // Дозволяємо невелику похибку округлення.
        assertEquals(t.targetKcal.toDouble(), kcalFromMacros.toDouble(), 30.0)
    }
}
