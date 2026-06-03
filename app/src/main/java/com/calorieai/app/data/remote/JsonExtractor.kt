package com.calorieai.app.data.remote

/** Витягання валідного JSON-об'єкта з тексту відповіді AI. */
object JsonExtractor {

    /**
     * Повертає підрядок від першої `{` до останньої `}` (на випадок, якщо модель
     * додала markdown чи пояснення навколо). null — якщо фігурних дужок немає.
     */
    fun extractObject(raw: String): String? {
        val cleaned = raw
            .replace("```json", "")
            .replace("```", "")
            .trim()
        val start = cleaned.indexOf('{')
        val end = cleaned.lastIndexOf('}')
        if (start < 0 || end <= start) return null
        return cleaned.substring(start, end + 1)
    }
}
