package com.calorieai.app

import com.calorieai.app.data.remote.JsonExtractor
import com.calorieai.app.data.remote.dto.AnalysisResult
import com.squareup.moshi.Moshi
import com.squareup.moshi.kotlin.reflect.KotlinJsonAdapterFactory
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class AnalysisParsingTest {

    private val moshi = Moshi.Builder().add(KotlinJsonAdapterFactory()).build()
    private val adapter = moshi.adapter(AnalysisResult::class.java)

    @Test
    fun `parses clean json`() {
        val json = """
            {"items":[{"name":"Рис","grams":200,"kcal":260,"protein":5.0,"fat":1.0,"carbs":57.0}],
            "total_kcal":260,"note":"ок"}
        """.trimIndent()
        val result = adapter.fromJson(json)
        assertNotNull(result)
        assertEquals(1, result!!.items.size)
        assertEquals("Рис", result.items.first().name)
        assertEquals(260, result.totalKcal)
    }

    @Test
    fun `extracts json from markdown fenced response`() {
        val raw = """
            Ось результат:
            ```json
            {"items":[{"name":"Яблуко","grams":150,"kcal":78,"protein":0.4,"fat":0.2,"carbs":21.0}],"total_kcal":78,"note":""}
            ```
            Сподіваюсь, це допоможе!
        """.trimIndent()
        val extracted = JsonExtractor.extractObject(raw)
        assertNotNull(extracted)
        val result = adapter.fromJson(extracted!!)
        assertNotNull(result)
        assertEquals("Яблуко", result!!.items.first().name)
        assertEquals(78, result.totalKcal)
    }

    @Test
    fun `extracts json surrounded by prose`() {
        val raw = "Звичайно. {\"items\":[],\"total_kcal\":0,\"note\":\"порожньо\"} Дякую."
        val extracted = JsonExtractor.extractObject(raw)
        assertNotNull(extracted)
        assertTrue(extracted!!.startsWith("{"))
        assertTrue(extracted.endsWith("}"))
    }

    @Test
    fun `returns null when no braces present`() {
        assertNull(JsonExtractor.extractObject("вибач, не можу допомогти"))
    }
}
