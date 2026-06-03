package com.calorieai.app.data.local.dao

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import com.calorieai.app.data.local.entity.AiCacheEntity

@Dao
interface AiCacheDao {
    @Query("SELECT * FROM ai_cache WHERE requestKey = :key LIMIT 1")
    suspend fun get(key: String): AiCacheEntity?

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun put(entity: AiCacheEntity)

    @Query("DELETE FROM ai_cache WHERE createdAt < :threshold")
    suspend fun deleteOlderThan(threshold: Long)
}
