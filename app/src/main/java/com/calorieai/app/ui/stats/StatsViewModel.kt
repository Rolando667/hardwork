package com.calorieai.app.ui.stats

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.calorieai.app.data.local.dao.DailyTotal
import com.calorieai.app.data.repository.DiaryRepository
import com.calorieai.app.data.repository.ProfileRepository
import com.calorieai.app.domain.NutritionCalculator
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.flatMapLatest
import kotlinx.coroutines.flow.stateIn
import javax.inject.Inject

enum class StatsRange(val days: Int) { WEEK(7), MONTH(30) }

data class StatsUiState(
    val range: StatsRange = StatsRange.WEEK,
    val totals: List<DailyTotal> = emptyList(),
    val targetKcal: Int? = null,
    val averageKcal: Int = 0,
    val daysLogged: Int = 0,
    val maxKcal: Int = 0
)

@OptIn(ExperimentalCoroutinesApi::class)
@HiltViewModel
class StatsViewModel @Inject constructor(
    diaryRepository: DiaryRepository,
    profileRepository: ProfileRepository
) : ViewModel() {

    private val range = MutableStateFlow(StatsRange.WEEK)

    private val totalsFlow = range.flatMapLatest { r ->
        diaryRepository.observeDailyTotals(r.days)
    }

    val uiState: StateFlow<StatsUiState> = combine(
        range,
        totalsFlow,
        profileRepository.observeProfile()
    ) { r, totals, profile ->
        val target = profile?.takeIf { it.isComplete }
            ?.let { NutritionCalculator.targetKcal(it) }
        val logged = totals.filter { it.kcal > 0 }
        StatsUiState(
            range = r,
            totals = totals,
            targetKcal = target,
            averageKcal = if (logged.isNotEmpty()) logged.sumOf { it.kcal } / logged.size else 0,
            daysLogged = logged.size,
            maxKcal = totals.maxOfOrNull { it.kcal } ?: 0
        )
    }.stateIn(
        scope = viewModelScope,
        started = SharingStarted.WhileSubscribed(5_000),
        initialValue = StatsUiState()
    )

    fun selectRange(newRange: StatsRange) {
        range.value = newRange
    }
}
