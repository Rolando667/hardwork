package com.calorieai.app.util

import android.app.NotificationChannel
import android.app.NotificationManager
import android.content.Context
import android.os.Build
import androidx.core.content.getSystemService

/** Канали сповіщень додатка. */
object Notifications {
    const val WATER_CHANNEL_ID = "water_reminder"
    const val WATER_NOTIFICATION_ID = 1001

    /** Створює канал нагадувань (потрібно для Android 8.0+). Викликати при старті. */
    fun createWaterChannel(context: Context) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
        val manager = context.getSystemService<NotificationManager>() ?: return
        val channel = NotificationChannel(
            WATER_CHANNEL_ID,
            "Нагадування пити воду",
            NotificationManager.IMPORTANCE_DEFAULT
        ).apply {
            description = "Нагадування про вживання води протягом дня"
        }
        manager.createNotificationChannel(channel)
    }
}
