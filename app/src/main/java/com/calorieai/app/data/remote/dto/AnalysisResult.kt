package com.calorieai.app.data.remote.dto

import com.calorieai.app.domain.model.FoodItem
import com.squareup.moshi.Json

/**
 * JSON-схема, яку повертає AI:
 * {"items":[{"name","grams","kcal","protein","fat","carbs"}],"total_kcal":0,"note":""}
 */
data class AnalysisResult(
    val items: List<AnalysisItem> = emptyList(),
    @Json(name = "total_kcal") val totalKcal: Int = 0,
    val note: String? = null
) {
    fun toFoodItems(): List<FoodItem> = items.map { it.toFoodItem() }
}

data class AnalysisItem(
    val name: String = "",
    val grams: Int = 0,
    val kcal: Int = 0,
    val protein: Double = 0.0,
    val fat: Double = 0.0,
    val carbs: Double = 0.0
) {
    fun toFoodItem(): FoodItem = FoodItem(
        name = name,
        grams = grams,
        kcal = kcal,
        protein = protein,
        fat = fat,
        carbs = carbs
    )
}
