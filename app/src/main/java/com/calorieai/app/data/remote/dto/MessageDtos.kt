package com.calorieai.app.data.remote.dto

import com.squareup.moshi.Json

/**
 * DTO для Anthropic Messages API (/v1/messages).
 * Null-поля Moshi не серіалізує, тож один [ContentBlock] обслуговує і текст, і фото.
 */
data class MessageRequest(
    val model: String,
    @Json(name = "max_tokens") val maxTokens: Int,
    val system: String,
    val messages: List<RequestMessage>
)

data class RequestMessage(
    val role: String,
    val content: List<ContentBlock>
)

data class ContentBlock(
    val type: String,
    val text: String? = null,
    val source: ImageSource? = null
) {
    companion object {
        fun text(value: String) = ContentBlock(type = "text", text = value)

        fun image(base64: String, mediaType: String) = ContentBlock(
            type = "image",
            source = ImageSource(
                type = "base64",
                mediaType = mediaType,
                data = base64
            )
        )
    }
}

data class ImageSource(
    val type: String,
    @Json(name = "media_type") val mediaType: String,
    val data: String
)

/** Відповідь API. Нас цікавить лише текст у блоках content. */
data class MessageResponse(
    val id: String?,
    val role: String?,
    val content: List<ResponseContentBlock>?,
    @Json(name = "stop_reason") val stopReason: String?
) {
    /** Об'єднаний текст усіх текстових блоків відповіді. */
    fun textContent(): String =
        content.orEmpty()
            .filter { it.type == "text" }
            .mapNotNull { it.text }
            .joinToString("\n")
            .trim()
}

data class ResponseContentBlock(
    val type: String,
    val text: String? = null
)
