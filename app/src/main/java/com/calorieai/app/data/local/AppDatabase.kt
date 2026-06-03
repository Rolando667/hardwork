package com.calorieai.app.data.local

import androidx.room.Database
import androidx.room.RoomDatabase
import androidx.room.TypeConverters
import com.calorieai.app.data.local.dao.AiCacheDao
import com.calorieai.app.data.local.dao.FoodEntryDao
import com.calorieai.app.data.local.dao.ProfileDao
import com.calorieai.app.data.local.entity.AiCacheEntity
import com.calorieai.app.data.local.entity.FoodEntryEntity
import com.calorieai.app.data.local.entity.UserProfileEntity

@Database(
    entities = [
        UserProfileEntity::class,
        FoodEntryEntity::class,
        AiCacheEntity::class
    ],
    version = 1,
    exportSchema = false
)
@TypeConverters(Converters::class)
abstract class AppDatabase : RoomDatabase() {
    abstract fun profileDao(): ProfileDao
    abstract fun foodEntryDao(): FoodEntryDao
    abstract fun aiCacheDao(): AiCacheDao

    companion object {
        const val NAME = "calorie_ai.db"
    }
}
