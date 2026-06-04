package com.calorieai.app.data.local.dao

import androidx.room.Dao
import androidx.room.Delete
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import androidx.room.Update
import com.calorieai.app.data.local.entity.FoodEntryEntity
import kotlinx.coroutines.flow.Flow
import java.time.LocalDate

@Dao
interface FoodEntryDao {
    @Query("SELECT * FROM food_entry WHERE date = :date ORDER BY createdAt ASC, id ASC")
    fun observeEntriesForDate(date: LocalDate): Flow<List<FoodEntryEntity>>

    @Query("DELETE FROM food_entry WHERE mealGroupId = :groupId")
    suspend fun deleteGroup(groupId: String)

    @Query("SELECT DISTINCT date FROM food_entry ORDER BY date DESC")
    fun observeDatesWithEntries(): Flow<List<LocalDate>>

    @Query(
        """
        SELECT date AS date, SUM(kcal) AS kcal, SUM(protein) AS protein,
               SUM(fat) AS fat, SUM(carbs) AS carbs
        FROM food_entry
        GROUP BY date
        ORDER BY date DESC
        LIMIT :limit
        """
    )
    fun observeDailyTotals(limit: Int): Flow<List<DailyTotal>>

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insert(entry: FoodEntryEntity): Long

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insertAll(entries: List<FoodEntryEntity>)

    @Update
    suspend fun update(entry: FoodEntryEntity)

    @Delete
    suspend fun delete(entry: FoodEntryEntity)
}
