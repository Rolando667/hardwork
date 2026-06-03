package com.calorieai.app.domain.model

import java.time.LocalDate

/** Джерело запису — звідки додано страву. */
enum class EntrySource { TEXT, PHOTO, MANUAL }

/** Збережений запис у щоденнику за конкретну дату. */
data class FoodEntry(
    val id: Long = 0L,
    val date: LocalDate,
    val name: String,
    val grams: Int,
    val kcal: Int,
    val protein: Double,
    val fat: Double,
    val carbs: Double,
    val source: EntrySource = EntrySource.MANUAL
)
