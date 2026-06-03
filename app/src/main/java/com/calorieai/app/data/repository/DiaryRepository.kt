package com.calorieai.app.data.repository

import com.calorieai.app.data.local.dao.FoodEntryDao
import com.calorieai.app.data.local.entity.FoodEntryEntity
import com.calorieai.app.domain.model.EntrySource
import com.calorieai.app.domain.model.FoodEntry
import com.calorieai.app.domain.model.FoodItem
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map
import java.time.LocalDate
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

    suspend fun add(entry: FoodEntry): Long =
        foodEntryDao.insert(FoodEntryEntity.fromDomain(entry))

    /** Додає одразу кілька позицій (результат AI-аналізу) за вказану дату. */
    suspend fun addItems(items: List<FoodItem>, date: LocalDate, source: EntrySource) {
        val entities = items.map {
            FoodEntryEntity(
                date = date,
                name = it.name,
                grams = it.grams,
                kcal = it.kcal,
                protein = it.protein,
                fat = it.fat,
                carbs = it.carbs,
                source = source
            )
        }
        foodEntryDao.insertAll(entities)
    }

    suspend fun update(entry: FoodEntry) =
        foodEntryDao.update(FoodEntryEntity.fromDomain(entry))

    suspend fun delete(entry: FoodEntry) =
        foodEntryDao.delete(FoodEntryEntity.fromDomain(entry))
}
