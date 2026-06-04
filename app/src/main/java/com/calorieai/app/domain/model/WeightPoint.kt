package com.calorieai.app.domain.model

import java.time.LocalDate

/** Точка ваги в часі для графіка динаміки. */
data class WeightPoint(
    val date: LocalDate,
    val weightKg: Double
)
