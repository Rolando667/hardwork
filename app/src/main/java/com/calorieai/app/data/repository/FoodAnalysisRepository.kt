package com.calorieai.app.data.repository

import android.content.Context
import android.net.Uri
import com.calorieai.app.R
import com.calorieai.app.data.local.dao.AiCacheDao
import com.calorieai.app.data.local.entity.AiCacheEntity
import com.calorieai.app.data.remote.AnthropicApi
import com.calorieai.app.data.remote.ApiKeyHolder
import com.calorieai.app.data.remote.JsonExtractor
import com.calorieai.app.data.remote.Prompts
import com.calorieai.app.data.remote.dto.AnalysisResult
import com.calorieai.app.data.remote.dto.ContentBlock
import com.calorieai.app.data.remote.dto.MessageRequest
import com.calorieai.app.data.remote.dto.RequestMessage
import com.calorieai.app.util.ImageUtils
import com.calorieai.app.util.OperationResult
import com.squareup.moshi.JsonAdapter
import com.squareup.moshi.Moshi
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.IOException
import java.security.MessageDigest
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Виконує AI-аналіз їжі (текст або фото) через Anthropic API, парсить JSON
 * через Moshi, кешує успішні результати та обробляє помилки.
 */
@Singleton
class FoodAnalysisRepository @Inject constructor(
    private val api: AnthropicApi,
    private val aiCacheDao: AiCacheDao,
    private val apiKeyHolder: ApiKeyHolder,
    moshi: Moshi,
    @ApplicationContext private val context: Context
) {
    private val adapter: JsonAdapter<AnalysisResult> =
        moshi.adapter(AnalysisResult::class.java)

    suspend fun analyzeText(foods: String): OperationResult<AnalysisResult> =
        withContext(Dispatchers.IO) {
            if (!hasApiKey()) return@withContext OperationResult.Error(R.string.error_no_api_key)

            val key = cacheKey("text", foods)
            cached(key)?.let { return@withContext OperationResult.Success(it) }

            val userContent = listOf(ContentBlock.text(Prompts.textRequest(foods)))
            runRequest(userContent, key)
        }

    suspend fun analyzePhoto(uri: Uri): OperationResult<AnalysisResult> =
        withContext(Dispatchers.IO) {
            if (!hasApiKey()) return@withContext OperationResult.Error(R.string.error_no_api_key)

            val encoded = ImageUtils.encodeForApi(context, uri)
                ?: return@withContext OperationResult.Error(R.string.error_unknown)

            val key = cacheKey("photo", encoded.base64)
            cached(key)?.let { return@withContext OperationResult.Success(it) }

            val userContent = listOf(
                ContentBlock.image(encoded.base64, encoded.mediaType),
                ContentBlock.text(Prompts.PHOTO_REQUEST)
            )
            runRequest(userContent, key)
        }

    /** Один запит до API з одним автоматичним повтором у разі невалідного JSON. */
    private suspend fun runRequest(
        userContent: List<ContentBlock>,
        cacheKey: String
    ): OperationResult<AnalysisResult> {
        val request = MessageRequest(
            model = AnthropicApi.MODEL,
            maxTokens = AnthropicApi.MAX_TOKENS,
            system = Prompts.SYSTEM,
            messages = listOf(RequestMessage(role = "user", content = userContent))
        )

        repeat(MAX_ATTEMPTS) { attempt ->
            val parsed = try {
                val response = api.createMessage(request)
                parse(response.textContent())
            } catch (e: IOException) {
                return OperationResult.Error(R.string.error_network, cause = e)
            } catch (e: retrofit2.HttpException) {
                // Сервер відповів помилкою (напр. 401 невірний ключ або 400 немає
                // коштів) — дістаємо й показуємо конкретне повідомлення.
                val body = runCatching { e.response()?.errorBody()?.string() }.getOrNull()
                val message = extractApiError(body) ?: "HTTP ${e.code()}"
                return OperationResult.Error(
                    R.string.error_unknown,
                    errorMessage = message,
                    cause = e
                )
            } catch (e: Exception) {
                if (attempt == MAX_ATTEMPTS - 1) {
                    return OperationResult.Error(
                        R.string.error_unknown,
                        errorMessage = e.message,
                        cause = e
                    )
                }
                null
            }

            if (parsed != null) {
                if (parsed.items.isEmpty()) {
                    return OperationResult.Error(R.string.error_ai_empty)
                }
                cache(cacheKey, parsed)
                return OperationResult.Success(parsed)
            }
        }
        return OperationResult.Error(R.string.error_ai_parse)
    }

    /** Витягає JSON із тексту та парсить його; null — якщо не валідний. */
    private fun parse(rawText: String): AnalysisResult? {
        val json = JsonExtractor.extractObject(rawText) ?: return null
        return try {
            adapter.fromJson(json)
        } catch (e: Exception) {
            null
        }
    }

    private suspend fun cached(key: String): AnalysisResult? {
        val entity = aiCacheDao.get(key) ?: return null
        return try {
            adapter.fromJson(entity.resultJson)
        } catch (e: Exception) {
            null
        }
    }

    private suspend fun cache(key: String, result: AnalysisResult) {
        aiCacheDao.put(
            AiCacheEntity(
                requestKey = key,
                resultJson = adapter.toJson(result),
                createdAt = System.currentTimeMillis()
            )
        )
    }

    /** Витягає поле error.message з тіла помилки Anthropic API. */
    private fun extractApiError(body: String?): String? {
        if (body.isNullOrBlank()) return null
        val match = Regex("\"message\"\\s*:\\s*\"(.*?)\"").find(body)
        return match?.groupValues?.get(1)?.takeIf { it.isNotBlank() }
    }

    private fun hasApiKey(): Boolean = apiKeyHolder.hasKey

    private fun cacheKey(prefix: String, payload: String): String {
        val digest = MessageDigest.getInstance("SHA-256")
            .digest(payload.toByteArray())
            .joinToString("") { "%02x".format(it) }
        return "$prefix:$digest"
    }

    private companion object {
        const val MAX_ATTEMPTS = 2
    }
}
