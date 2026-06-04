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
import androidx.work.Worker
import androidx.work.WorkerParameters
import com.calorieai.app.MainActivity
import com.calorieai.app.R
import com.calorieai.app.util.CalendarReader
import com.calorieai.app.util.Notifications

/** Показує сповіщення-нагадування випити склянку води. */
class WaterReminderWorker(
    context: Context,
    params: WorkerParameters
) : Worker(context, params) {

    override fun doWork(): Result {
        val context = applicationContext

        // Якщо увімкнено пропуск під час зустрічей і зараз триває зустріч — мовчимо.
        val skipDuringMeetings = inputData.getBoolean(KEY_SKIP_MEETINGS, false)
        if (skipDuringMeetings && CalendarReader.isBusyNow(context)) {
            return Result.success()
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

    companion object {
        const val KEY_SKIP_MEETINGS = "skip_meetings"
    }
}
