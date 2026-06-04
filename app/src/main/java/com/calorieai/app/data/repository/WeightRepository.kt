package com.calorieai.app.data.repository

import com.calorieai.app.data.local.dao.WeightDao
import com.calorieai.app.data.local.entity.WeightEntryEntity
import com.calorieai.app.domain.model.WeightPoint
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map
import java.time.LocalDate
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class WeightRepository @Inject constructor(
    private val weightDao: WeightDao
) {
    fun observeAll(): Flow<List<WeightPoint>> =
        weightDao.observeAll().map { list -> list.map { it.toDomain() } }

    suspend fun add(date: LocalDate, weightKg: Double) =
        weightDao.upsert(WeightEntryEntity(date = date, weightKg = weightKg))

    suspend fun delete(date: LocalDate) = weightDao.delete(date)
}
