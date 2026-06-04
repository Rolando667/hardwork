package com.calorieai.app.work

import android.content.Context
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.workDataOf
import dagger.hilt.android.qualifiers.ApplicationContext
import java.util.concurrent.TimeUnit
import javax.inject.Inject
import javax.inject.Singleton

/** Планує/скасовує періодичні нагадування пити воду через WorkManager. */
@Singleton
class WaterReminderScheduler @Inject constructor(
    @ApplicationContext private val context: Context
) {
    fun schedule(intervalHours: Int, skipDuringMeetings: Boolean) {
        // WorkManager має мінімальний період 15 хв; обмежуємо знизу.
        val hours = intervalHours.coerceIn(1, 12)
        val request = PeriodicWorkRequestBuilder<WaterReminderWorker>(
            hours.toLong(), TimeUnit.HOURS
        ).setInputData(
            workDataOf(WaterReminderWorker.KEY_SKIP_MEETINGS to skipDuringMeetings)
        ).build()

        WorkManager.getInstance(context).enqueueUniquePeriodicWork(
            WORK_NAME,
            ExistingPeriodicWorkPolicy.UPDATE,
            request
        )
    }

    fun cancel() {
        WorkManager.getInstance(context).cancelUniqueWork(WORK_NAME)
    }

    private companion object {
        const val WORK_NAME = "water_reminder_work"
    }
}
