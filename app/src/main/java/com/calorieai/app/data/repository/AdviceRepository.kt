package com.calorieai.app.data.repository

import com.calorieai.app.R
import com.calorieai.app.data.remote.AnthropicApi
import com.calorieai.app.data.remote.ApiKeyHolder
import com.calorieai.app.data.remote.Prompts
import com.calorieai.app.data.remote.dto.ContentBlock
import com.calorieai.app.data.remote.dto.MessageRequest
import com.calorieai.app.data.remote.dto.RequestMessage
import com.calorieai.app.util.OperationResult
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.IOException
import javax.inject.Inject
import javax.inject.Singleton

/** Генерує текстову пораду нутриціолога на основі підсумку раціону. */
@Singleton
class AdviceRepository @Inject constructor(
    private val api: AnthropicApi,
    private val apiKeyHolder: ApiKeyHolder
) {
    suspend fun getAdvice(summary: String): OperationResult<String> =
        withContext(Dispatchers.IO) {
            if (!apiKeyHolder.hasKey) {
                return@withContext OperationResult.Error(R.string.error_no_api_key)
            }

            val request = MessageRequest(
                model = AnthropicApi.MODEL,
                maxTokens = 600,
                system = Prompts.ADVICE_SYSTEM,
                messages = listOf(
                    RequestMessage(role = "user", content = listOf(ContentBlock.text(summary)))
                )
            )

            try {
                val text = api.createMessage(request).textContent()
                if (text.isBlank()) {
                    OperationResult.Error(R.string.error_unknown)
                } else {
                    OperationResult.Success(text)
                }
            } catch (e: IOException) {
                OperationResult.Error(R.string.error_network, cause = e)
            } catch (e: retrofit2.HttpException) {
                val body = runCatching { e.response()?.errorBody()?.string() }.getOrNull()
                val message = extractApiError(body) ?: "HTTP ${e.code()}"
                OperationResult.Error(R.string.error_unknown, errorMessage = message, cause = e)
            } catch (e: Exception) {
                OperationResult.Error(R.string.error_unknown, errorMessage = e.message, cause = e)
            }
        }

    private fun extractApiError(body: String?): String? {
        if (body.isNullOrBlank()) return null
        return Regex("\"message\"\\s*:\\s*\"(.*?)\"").find(body)
            ?.groupValues?.get(1)?.takeIf { it.isNotBlank() }
    }
}
