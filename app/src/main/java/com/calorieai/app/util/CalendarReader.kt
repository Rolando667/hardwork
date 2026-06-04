package com.calorieai.app.util

import android.Manifest
import android.content.ContentUris
import android.content.Context
import android.content.pm.PackageManager
import android.provider.CalendarContract
import androidx.core.content.ContextCompat

/**
 * Читає системний календар (куди синхронізується Google Календар), щоб визначити,
 * чи зайнятий користувач зустріччю прямо зараз. Не потребує входу через Google —
 * лише дозволу READ_CALENDAR.
 */
object CalendarReader {

    fun hasPermission(context: Context): Boolean =
        ContextCompat.checkSelfPermission(
            context, Manifest.permission.READ_CALENDAR
        ) == PackageManager.PERMISSION_GRANTED

    /**
     * true — якщо зараз триває зустріч (подія, що перетинається з поточним моментом).
     * Події на весь день та позначені «вільний» (Free) ігноруються.
     */
    fun isBusyNow(context: Context): Boolean {
        if (!hasPermission(context)) return false

        val now = System.currentTimeMillis()
        val builder = CalendarContract.Instances.CONTENT_URI.buildUpon()
        ContentUris.appendId(builder, now)
        ContentUris.appendId(builder, now + ONE_MINUTE_MS)

        val projection = arrayOf(
            CalendarContract.Instances.ALL_DAY,
            CalendarContract.Instances.AVAILABILITY
        )

        return try {
            context.contentResolver.query(builder.build(), projection, null, null, null)
                ?.use { cursor ->
                    while (cursor.moveToNext()) {
                        val allDay = cursor.getInt(0) == 1
                        val availability = cursor.getInt(1)
                        if (allDay) continue
                        if (availability == CalendarContract.Instances.AVAILABILITY_FREE) continue
                        return true
                    }
                    false
                } ?: false
        } catch (e: SecurityException) {
            false
        }
    }

    private const val ONE_MINUTE_MS = 60_000L
}
