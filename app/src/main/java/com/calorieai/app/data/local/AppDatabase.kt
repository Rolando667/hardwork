package com.calorieai.app.data.local

import androidx.room.Database
import androidx.room.RoomDatabase
import androidx.room.TypeConverters
import androidx.room.migration.Migration
import androidx.sqlite.db.SupportSQLiteDatabase
import com.calorieai.app.data.local.dao.AiCacheDao
import com.calorieai.app.data.local.dao.FoodEntryDao
import com.calorieai.app.data.local.dao.ProfileDao
import com.calorieai.app.data.local.dao.WeightDao
import com.calorieai.app.data.local.entity.AiCacheEntity
import com.calorieai.app.data.local.entity.FoodEntryEntity
import com.calorieai.app.data.local.entity.UserProfileEntity
import com.calorieai.app.data.local.entity.WeightEntryEntity

@Database(
    entities = [
        UserProfileEntity::class,
        FoodEntryEntity::class,
        AiCacheEntity::class,
        WeightEntryEntity::class
    ],
    version = 3,
    exportSchema = false
)
@TypeConverters(Converters::class)
abstract class AppDatabase : RoomDatabase() {
    abstract fun profileDao(): ProfileDao
    abstract fun foodEntryDao(): FoodEntryDao
    abstract fun aiCacheDao(): AiCacheDao
    abstract fun weightDao(): WeightDao

    companion object {
        const val NAME = "calorie_ai.db"

        /** Додає таблицю ваги без втрати наявних даних (профіль, записи). */
        val MIGRATION_1_2 = object : Migration(1, 2) {
            override fun migrate(db: SupportSQLiteDatabase) {
                db.execSQL(
                    "CREATE TABLE IF NOT EXISTS `weight_entry` (" +
                        "`date` TEXT NOT NULL, `weightKg` REAL NOT NULL, " +
                        "PRIMARY KEY(`date`))"
                )
            }
        }

        /** Додає до записів прийом їжі, групу страви та час створення. */
        val MIGRATION_2_3 = object : Migration(2, 3) {
            override fun migrate(db: SupportSQLiteDatabase) {
                db.execSQL(
                    "ALTER TABLE `food_entry` ADD COLUMN `mealType` TEXT NOT NULL " +
                        "DEFAULT 'SNACK'"
                )
                db.execSQL(
                    "ALTER TABLE `food_entry` ADD COLUMN `mealGroupId` TEXT NOT NULL " +
                        "DEFAULT ''"
                )
                db.execSQL(
                    "ALTER TABLE `food_entry` ADD COLUMN `createdAt` INTEGER NOT NULL " +
                        "DEFAULT 0"
                )
                // Кожен наявний запис стає окремою «стравою» зі стабільним порядком.
                db.execSQL("UPDATE `food_entry` SET `mealGroupId` = 'legacy_' || `id`")
                db.execSQL("UPDATE `food_entry` SET `createdAt` = `id`")
            }
        }
    }
}
