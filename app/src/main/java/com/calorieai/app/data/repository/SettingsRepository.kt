package com.calorieai.app.data.repository

import android.content.Context
import androidx.datastore.preferences.core.booleanPreferencesKey
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.intPreferencesKey
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import com.calorieai.app.domain.model.ThemeMode
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map
import javax.inject.Inject
import javax.inject.Singleton

private val Context.dataStore by preferencesDataStore(name = "settings")

/** Налаштування додатка: тема, AI-ключ та нагадування пити воду. */
data class AppSettings(
    val themeMode: ThemeMode = ThemeMode.SYSTEM,
    val dynamicColor: Boolean = true,
    val apiKey: String = "",
    val waterReminderEnabled: Boolean = false,
    val waterIntervalHours: Int = DEFAULT_WATER_INTERVAL_HOURS
) {
    companion object {
        const val DEFAULT_WATER_INTERVAL_HOURS = 2
    }
}

@Singleton
class SettingsRepository @Inject constructor(
    @ApplicationContext private val context: Context
) {
    private object Keys {
        val THEME_MODE = stringPreferencesKey("theme_mode")
        val DYNAMIC_COLOR = booleanPreferencesKey("dynamic_color")
        val API_KEY = stringPreferencesKey("api_key")
        val WATER_ENABLED = booleanPreferencesKey("water_reminder_enabled")
        val WATER_INTERVAL = intPreferencesKey("water_interval_hours")
    }

    val settings: Flow<AppSettings> = context.dataStore.data.map { prefs ->
        AppSettings(
            themeMode = prefs[Keys.THEME_MODE]
                ?.let { runCatching { ThemeMode.valueOf(it) }.getOrNull() }
                ?: ThemeMode.SYSTEM,
            dynamicColor = prefs[Keys.DYNAMIC_COLOR] ?: true,
            apiKey = prefs[Keys.API_KEY] ?: "",
            waterReminderEnabled = prefs[Keys.WATER_ENABLED] ?: false,
            waterIntervalHours = prefs[Keys.WATER_INTERVAL]
                ?: AppSettings.DEFAULT_WATER_INTERVAL_HOURS
        )
    }

    suspend fun setThemeMode(mode: ThemeMode) {
        context.dataStore.edit { it[Keys.THEME_MODE] = mode.name }
    }

    suspend fun setDynamicColor(enabled: Boolean) {
        context.dataStore.edit { it[Keys.DYNAMIC_COLOR] = enabled }
    }

    suspend fun setApiKey(key: String) {
        context.dataStore.edit { it[Keys.API_KEY] = key.trim() }
    }

    suspend fun setWaterReminderEnabled(enabled: Boolean) {
        context.dataStore.edit { it[Keys.WATER_ENABLED] = enabled }
    }

    suspend fun setWaterIntervalHours(hours: Int) {
        context.dataStore.edit { it[Keys.WATER_INTERVAL] = hours }
    }
}
