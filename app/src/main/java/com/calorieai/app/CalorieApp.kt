package com.calorieai.app

import android.app.Application
import com.calorieai.app.data.remote.ApiKeyHolder
import com.calorieai.app.data.repository.SettingsRepository
import com.calorieai.app.util.Notifications
import com.calorieai.app.work.WaterReminderScheduler
import dagger.hilt.android.HiltAndroidApp
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.flow.distinctUntilChanged
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.launch
import javax.inject.Inject

private data class WaterConfig(
    val enabled: Boolean,
    val intervalHours: Int,
    val skipDuringMeetings: Boolean
)

@HiltAndroidApp
class CalorieApp : Application() {

    @Inject lateinit var settingsRepository: SettingsRepository
    @Inject lateinit var apiKeyHolder: ApiKeyHolder
    @Inject lateinit var waterScheduler: WaterReminderScheduler

    private val appScope = CoroutineScope(SupervisorJob() + Dispatchers.Default)

    override fun onCreate() {
        super.onCreate()
        Notifications.createWaterChannel(this)

        // Тримаємо AI-ключ у пам'яті в актуальному стані.
        appScope.launch {
            settingsRepository.settings
                .map { it.apiKey }
                .distinctUntilChanged()
                .collect { apiKeyHolder.update(it) }
        }

        // Плануємо/скасовуємо нагадування пити воду згідно з налаштуваннями.
        appScope.launch {
            settingsRepository.settings
                .map {
                    WaterConfig(it.waterReminderEnabled, it.waterIntervalHours, it.skipDuringMeetings)
                }
                .distinctUntilChanged()
                .collect { config ->
                    if (config.enabled) {
                        waterScheduler.schedule(config.intervalHours, config.skipDuringMeetings)
                    } else {
                        waterScheduler.cancel()
                    }
                }
        }
    }
}
