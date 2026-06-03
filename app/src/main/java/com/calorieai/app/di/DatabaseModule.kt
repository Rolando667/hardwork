package com.calorieai.app.di

import android.content.Context
import androidx.room.Room
import com.calorieai.app.data.local.AppDatabase
import com.calorieai.app.data.local.dao.AiCacheDao
import com.calorieai.app.data.local.dao.FoodEntryDao
import com.calorieai.app.data.local.dao.ProfileDao
import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.android.qualifiers.ApplicationContext
import dagger.hilt.components.SingletonComponent
import javax.inject.Singleton

@Module
@InstallIn(SingletonComponent::class)
object DatabaseModule {

    @Provides
    @Singleton
    fun provideDatabase(@ApplicationContext context: Context): AppDatabase =
        Room.databaseBuilder(context, AppDatabase::class.java, AppDatabase.NAME)
            .fallbackToDestructiveMigration()
            .build()

    @Provides
    fun provideProfileDao(db: AppDatabase): ProfileDao = db.profileDao()

    @Provides
    fun provideFoodEntryDao(db: AppDatabase): FoodEntryDao = db.foodEntryDao()

    @Provides
    fun provideAiCacheDao(db: AppDatabase): AiCacheDao = db.aiCacheDao()
}
