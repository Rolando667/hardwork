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

    /** true — якщо зараз триває зустріч (подія, що перетинається з поточним моментом). */
    fun isBusyNow(context: Context): Boolean = currentMeetingEndMillis(context) != null

    /**
     * Час завершення зустрічі, що триває зараз (epoch millis), або null — якщо вільно.
     * Якщо зустрічей кілька (накладаються), повертає найпізніше завершення.
     * Події на весь день та позначені «вільний» (Free) ігноруються.
     */
    fun currentMeetingEndMillis(context: Context): Long? {
        if (!hasPermission(context)) return null

        val now = System.currentTimeMillis()
        val builder = CalendarContract.Instances.CONTENT_URI.buildUpon()
        ContentUris.appendId(builder, now)
        ContentUris.appendId(builder, now + ONE_MINUTE_MS)

        val projection = arrayOf(
            CalendarContract.Instances.END,
            CalendarContract.Instances.ALL_DAY,
            CalendarContract.Instances.AVAILABILITY
        )

        return try {
            context.contentResolver.query(builder.build(), projection, null, null, null)
                ?.use { cursor ->
                    var latestEnd: Long? = null
                    while (cursor.moveToNext()) {
                        val end = cursor.getLong(0)
                        val allDay = cursor.getInt(1) == 1
                        val availability = cursor.getInt(2)
                        if (allDay) continue
                        if (availability == CalendarContract.Instances.AVAILABILITY_FREE) continue
                        if (end > now && (latestEnd == null || end > latestEnd!!)) {
                            latestEnd = end
                        }
                    }
                    latestEnd
                }
        } catch (e: SecurityException) {
            null
        }
    }

    private const val ONE_MINUTE_MS = 60_000L
}
