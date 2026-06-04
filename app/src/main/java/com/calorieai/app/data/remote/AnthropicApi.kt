package com.calorieai.app.data.remote

import com.calorieai.app.data.remote.dto.MessageRequest
import com.calorieai.app.data.remote.dto.MessageResponse
import retrofit2.http.Body
import retrofit2.http.POST

/** Retrofit-інтерфейс Anthropic Messages API. */
interface AnthropicApi {
    @POST("v1/messages")
    suspend fun createMessage(@Body request: MessageRequest): MessageResponse

    companion object {
        const val BASE_URL = "https://api.anthropic.com/"
        const val MODEL = "claude-sonnet-4-6"
        const val ANTHROPIC_VERSION = "2023-06-01"
        const val MAX_TOKENS = 1024
    }
}
