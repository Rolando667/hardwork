package com.calorieai.app.data.local.entity

import androidx.room.Entity
import androidx.room.PrimaryKey
import com.calorieai.app.domain.model.ActivityLevel
import com.calorieai.app.domain.model.Goal
import com.calorieai.app.domain.model.Sex
import com.calorieai.app.domain.model.UserProfile

/** Профіль зберігається одним рядком із фіксованим id = 0. */
@Entity(tableName = "user_profile")
data class UserProfileEntity(
    @PrimaryKey val id: Int = SINGLETON_ID,
    val age: Int,
    val sex: Sex,
    val heightCm: Int,
    val weightKg: Double,
    val activityLevel: ActivityLevel,
    val goal: Goal
) {
    fun toDomain(): UserProfile = UserProfile(
        age = age,
        sex = sex,
        heightCm = heightCm,
        weightKg = weightKg,
        activityLevel = activityLevel,
        goal = goal
    )

    companion object {
        const val SINGLETON_ID = 0

        fun fromDomain(profile: UserProfile): UserProfileEntity = UserProfileEntity(
            id = SINGLETON_ID,
            age = profile.age,
            sex = profile.sex,
            heightCm = profile.heightCm,
            weightKg = profile.weightKg,
            activityLevel = profile.activityLevel,
            goal = profile.goal
        )
    }
}
