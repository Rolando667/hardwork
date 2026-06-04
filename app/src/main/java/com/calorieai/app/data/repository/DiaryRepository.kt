package com.calorieai.app.data.repository

import com.calorieai.app.data.local.dao.DailyTotal
import com.calorieai.app.data.local.dao.FoodEntryDao
import com.calorieai.app.data.local.entity.FoodEntryEntity
import com.calorieai.app.domain.model.EntrySource
import com.calorieai.app.domain.model.FoodEntry
import com.calorieai.app.domain.model.FoodItem
import com.calorieai.app.domain.model.MealType
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map
import java.time.LocalDate
import java.util.UUID
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class DiaryRepository @Inject constructor(
    private val foodEntryDao: FoodEntryDao
) {
    fun observeEntriesForDate(date: LocalDate): Flow<List<FoodEntry>> =
        foodEntryDao.observeEntriesForDate(date).map { list -> list.map { it.toDomain() } }

    fun observeDatesWithEntries(): Flow<List<LocalDate>> =
        foodEntryDao.observeDatesWithEntries()

    fun observeDailyTotals(limit: Int): Flow<List<DailyTotal>> =
        foodEntryDao.observeDailyTotals(limit)

    suspend fun add(entry: FoodEntry): Long =
        foodEntryDao.insert(FoodEntryEntity.fromDomain(entry))

    /**
     * Додає кілька позицій як одну страву/прийом їжі: усі отримують спільний
     * mealGroupId, тип прийому та час створення.
     */
    suspend fun addMeal(
        items: List<FoodItem>,
        date: LocalDate,
        mealType: MealType,
        source: EntrySource
    ) {
        val groupId = UUID.randomUUID().toString()
        val now = System.currentTimeMillis()
        val entities = items.map {
            FoodEntryEntity(
                date = date,
                name = it.name,
                grams = it.grams,
                kcal = it.kcal,
                protein = it.protein,
                fat = it.fat,
                carbs = it.carbs,
                source = source,
                mealType = mealType,
                mealGroupId = groupId,
                createdAt = now
            )
        }
        foodEntryDao.insertAll(entities)
    }

    /** Повторне додавання раніше видалених записів (для скасування). */
    suspend fun addEntries(entries: List<FoodEntry>) {
        foodEntryDao.insertAll(entries.map { FoodEntryEntity.fromDomain(it).copy(id = 0L) })
    }

    suspend fun update(entry: FoodEntry) =
        foodEntryDao.update(FoodEntryEntity.fromDomain(entry))

    suspend fun delete(entry: FoodEntry) =
        foodEntryDao.delete(FoodEntryEntity.fromDomain(entry))

    suspend fun deleteGroup(groupId: String) = foodEntryDao.deleteGroup(groupId)
}
