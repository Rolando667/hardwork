package com.calorieai.app.data.remote

import com.calorieai.app.BuildConfig
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Тримає актуальний AI-ключ у пам'яті, щоб OkHttp-інтерсептор міг читати його
 * синхронно під час кожного запиту. Значення оновлюється з DataStore при старті
 * та після зміни ключа в налаштуваннях. Якщо користувач не ввів ключ, береться
 * запасний з BuildConfig (для збірок із «вшитим» ключем).
 */
@Singleton
class ApiKeyHolder @Inject constructor() {
    @Volatile
    var key: String = BuildConfig.ANTHROPIC_API_KEY

    /** Оновлення з налаштувань: введений ключ має пріоритет над BuildConfig. */
    fun update(userKey: String) {
        key = userKey.ifBlank { BuildConfig.ANTHROPIC_API_KEY }
    }

    val hasKey: Boolean get() = key.isNotBlank()
}
