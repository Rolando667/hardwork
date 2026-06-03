package com.calorieai.app.data.repository

import com.calorieai.app.data.local.dao.ProfileDao
import com.calorieai.app.data.local.entity.UserProfileEntity
import com.calorieai.app.domain.model.UserProfile
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class ProfileRepository @Inject constructor(
    private val profileDao: ProfileDao
) {
    /** Профіль або null, якщо ще не заповнено. */
    fun observeProfile(): Flow<UserProfile?> =
        profileDao.observeProfile().map { it?.toDomain() }

    suspend fun getProfile(): UserProfile? = profileDao.getProfile()?.toDomain()

    suspend fun save(profile: UserProfile) {
        profileDao.upsert(UserProfileEntity.fromDomain(profile))
    }
}
