package com.calorieai.app.work

import android.Manifest
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.ContextCompat
import androidx.work.ExistingWorkPolicy
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.Worker
import androidx.work.WorkerParameters
import androidx.work.workDataOf
import com.calorieai.app.MainActivity
import com.calorieai.app.R
import com.calorieai.app.util.CalendarReader
import com.calorieai.app.util.Notifications
import java.util.concurrent.TimeUnit

/** Показує сповіщення-нагадування випити склянку води. */
class WaterReminderWorker(
    context: Context,
    params: WorkerParameters
) : Worker(context, params) {

    override fun doWork(): Result {
        val context = applicationContext

        val skipDuringMeetings = inputData.getBoolean(KEY_SKIP_MEETINGS, false)
        val isFollowup = inputData.getBoolean(KEY_IS_FOLLOWUP, false)

        // Якщо увімкнено пропуск під час зустрічей і зараз триває зустріч — не
        // нагадуємо зараз, а переносимо нагадування на 10 хв після її завершення.
        if (skipDuringMeetings) {
            val meetingEnd = CalendarReader.currentMeetingEndMillis(context)
            if (meetingEnd != null) {
                scheduleAfterMeeting(context, meetingEnd)
                return Result.success()
            }
        }

        // Вільний час: показуємо нагадування. Якщо це звичайне (періодичне)
        // спрацювання — скасовуємо стару відкладену спробу, щоб вона не показалась
        // пізніше (вже настав час свіжого нагадування — старе не потрібне).
        if (!isFollowup) {
            WorkManager.getInstance(context).cancelUniqueWork(FOLLOWUP_WORK_NAME)
        }

        // На Android 13+ потрібен дозвіл POST_NOTIFICATIONS.
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            val granted = ContextCompat.checkSelfPermission(
                context, Manifest.permission.POST_NOTIFICATIONS
            ) == PackageManager.PERMISSION_GRANTED
            if (!granted) return Result.success()
        }

        val launchIntent = Intent(context, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP
        }
        val pendingIntent = PendingIntent.getActivity(
            context,
            0,
            launchIntent,
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
        )

        val notification = NotificationCompat.Builder(context, Notifications.WATER_CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_water_drop)
            .setContentTitle(context.getString(R.string.water_notif_title))
            .setContentText(context.getString(R.string.water_notif_text))
            .setPriority(NotificationCompat.PRIORITY_DEFAULT)
            .setAutoCancel(true)
            .setContentIntent(pendingIntent)
            .build()

        NotificationManagerCompat.from(context)
            .notify(Notifications.WATER_NOTIFICATION_ID, notification)

        return Result.success()
    }

    /**
     * Планує одноразове нагадування через 10 хв після завершення зустрічі.
     * Коли воно спрацює, перевірка зустрічі повториться: якщо почалася нова —
     * нагадування знову відкладеться до її кінця (ланцюжок переносів).
     */
    private fun scheduleAfterMeeting(context: Context, meetingEndMillis: Long) {
        val delayMs = (meetingEndMillis - System.currentTimeMillis() + AFTER_MEETING_DELAY_MS)
            .coerceAtLeast(ONE_MINUTE_MS)

        val followUp = OneTimeWorkRequestBuilder<WaterReminderWorker>()
            .setInitialDelay(delayMs, TimeUnit.MILLISECONDS)
            .setInputData(
                workDataOf(KEY_SKIP_MEETINGS to true, KEY_IS_FOLLOWUP to true)
            )
            .build()

        WorkManager.getInstance(context).enqueueUniqueWork(
            FOLLOWUP_WORK_NAME,
            ExistingWorkPolicy.REPLACE,
            followUp
        )
    }

    companion object {
        const val KEY_SKIP_MEETINGS = "skip_meetings"
        const val KEY_IS_FOLLOWUP = "is_followup"
        private const val FOLLOWUP_WORK_NAME = "water_reminder_followup"
        private const val AFTER_MEETING_DELAY_MS = 10 * 60_000L
        private const val ONE_MINUTE_MS = 60_000L
    }
}
