package com.calorieai.app.data.local.entity

import androidx.room.Entity
import androidx.room.Index
import androidx.room.PrimaryKey
import com.calorieai.app.domain.model.EntrySource
import com.calorieai.app.domain.model.FoodEntry
import com.calorieai.app.domain.model.MealType
import java.time.LocalDate

@Entity(
    tableName = "food_entry",
    indices = [Index("date")]
)
data class FoodEntryEntity(
    @PrimaryKey(autoGenerate = true) val id: Long = 0L,
    val date: LocalDate,
    val name: String,
    val grams: Int,
    val kcal: Int,
    val protein: Double,
    val fat: Double,
    val carbs: Double,
    val source: EntrySource,
    val mealType: MealType = MealType.SNACK,
    val mealGroupId: String = "",
    val createdAt: Long = 0L
) {
    fun toDomain(): FoodEntry = FoodEntry(
        id = id,
        date = date,
        name = name,
        grams = grams,
        kcal = kcal,
        protein = protein,
        fat = fat,
        carbs = carbs,
        source = source,
        mealType = mealType,
        mealGroupId = mealGroupId,
        createdAt = createdAt
    )

    companion object {
        fun fromDomain(entry: FoodEntry): FoodEntryEntity = FoodEntryEntity(
            id = entry.id,
            date = entry.date,
            name = entry.name,
            grams = entry.grams,
            kcal = entry.kcal,
            protein = entry.protein,
            fat = entry.fat,
            carbs = entry.carbs,
            source = entry.source,
            mealType = entry.mealType,
            mealGroupId = entry.mealGroupId,
            createdAt = entry.createdAt
        )
    }
}
