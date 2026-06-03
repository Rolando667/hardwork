package com.calorieai.app.data.local.entity

import androidx.room.Entity
import androidx.room.PrimaryKey

/**
 * Кеш відповідей AI. [requestKey] — хеш від тексту запиту або зображення,
 * [resultJson] — серіалізований AnalysisResult.
 */
@Entity(tableName = "ai_cache")
data class AiCacheEntity(
    @PrimaryKey val requestKey: String,
    val resultJson: String,
    val createdAt: Long
)
