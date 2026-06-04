package com.calorieai.app.data.local.entity

import androidx.room.Entity
import androidx.room.PrimaryKey
import com.calorieai.app.domain.model.WeightPoint
import java.time.LocalDate

/** Одне зважування на дату (повторне за той самий день перезаписує попереднє). */
@Entity(tableName = "weight_entry")
data class WeightEntryEntity(
    @PrimaryKey val date: LocalDate,
    val weightKg: Double
) {
    fun toDomain(): WeightPoint = WeightPoint(date, weightKg)
}
