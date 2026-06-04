package com.calorieai.app.ui.stats

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.calorieai.app.data.local.dao.DailyTotal
import com.calorieai.app.data.repository.AdviceRepository
import com.calorieai.app.data.repository.DiaryRepository
import com.calorieai.app.data.repository.ProfileRepository
import com.calorieai.app.data.repository.WeightRepository
import com.calorieai.app.domain.NutritionCalculator
import com.calorieai.app.domain.model.WeightPoint
import com.calorieai.app.util.OperationResult
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.flatMapLatest
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch
import java.time.LocalDate
import javax.inject.Inject
import kotlin.math.roundToInt

enum class StatsRange(val days: Int) { WEEK(7), MONTH(30) }

data class StatsUiState(
    val range: StatsRange = StatsRange.WEEK,
    val totals: List<DailyTotal> = emptyList(),
    val targetKcal: Int? = null,
    val averageKcal: Int = 0,
    val daysLogged: Int = 0,
    val maxKcal: Int = 0,
    val weightPoints: List<WeightPoint> = emptyList(),
    val latestWeight: Double? = null,
    val weightDelta: Double? = null
)

sealed interface AdviceState {
    data object Idle : AdviceState
    data object Loading : AdviceState
    data class Success(val text: String) : AdviceState
    data class Error(val errorRes: Int, val errorMessage: String?) : AdviceState
}

@OptIn(ExperimentalCoroutinesApi::class)
@HiltViewModel
class StatsViewModel @Inject constructor(
    private val diaryRepository: DiaryRepository,
    private val profileRepository: ProfileRepository,
    private val weightRepository: WeightRepository,
    private val adviceRepository: AdviceRepository
) : ViewModel() {

    private val range = MutableStateFlow(StatsRange.WEEK)

    private val _adviceState = MutableStateFlow<AdviceState>(AdviceState.Idle)
    val adviceState: StateFlow<AdviceState> = _adviceState.asStateFlow()

    private val totalsFlow = range.flatMapLatest { r ->
        diaryRepository.observeDailyTotals(r.days)
    }

    val uiState: StateFlow<StatsUiState> = combine(
        range,
        totalsFlow,
        profileRepository.observeProfile(),
        weightRepository.observeAll()
    ) { r, totals, profile, weights ->
        val target = profile?.takeIf { it.isComplete }
            ?.let { NutritionCalculator.targetKcal(it) }
        val logged = totals.filter { it.kcal > 0 }
        StatsUiState(
            range = r,
            totals = totals,
            targetKcal = target,
            averageKcal = if (logged.isNotEmpty()) logged.sumOf { it.kcal } / logged.size else 0,
            daysLogged = logged.size,
            maxKcal = totals.maxOfOrNull { it.kcal } ?: 0,
            weightPoints = weights,
            latestWeight = weights.lastOrNull()?.weightKg,
            weightDelta = if (weights.size >= 2) {
                weights.last().weightKg - weights.first().weightKg
            } else null
        )
    }.stateIn(
        scope = viewModelScope,
        started = SharingStarted.WhileSubscribed(5_000),
        initialValue = StatsUiState()
    )

    fun selectRange(newRange: StatsRange) {
        range.value = newRange
    }

    /** Генерує AI-пораду на основі підсумку раціону за обраний період. */
    fun generateAdvice() {
        val state = uiState.value
        _adviceState.value = AdviceState.Loading
        viewModelScope.launch {
            when (val result = adviceRepository.getAdvice(buildSummary(state))) {
                is OperationResult.Success ->
                    _adviceState.value = AdviceState.Success(result.data)
                is OperationResult.Error ->
                    _adviceState.value = AdviceState.Error(result.errorRes, result.errorMessage)
                OperationResult.Loading -> Unit
            }
        }
    }

    private fun buildSummary(state: StatsUiState): String {
        val rangeLabel = if (state.range == StatsRange.WEEK) "тиждень" else "місяць"
        val logged = state.totals.filter { it.kcal > 0 }
        val days = logged.size.coerceAtLeast(1)
        val avgProtein = (logged.sumOf { it.protein } / days).roundToInt()
        val avgFat = (logged.sumOf { it.fat } / days).roundToInt()
        val avgCarbs = (logged.sumOf { it.carbs } / days).roundToInt()

        return buildString {
            appendLine("Період аналізу: $rangeLabel.")
            appendLine("Днів із записами: ${logged.size}.")
            state.targetKcal?.let { appendLine("Денна норма калорій: $it ккал.") }
            appendLine("Середнє спожито: ${state.averageKcal} ккал/день.")
            appendLine(
                "Середні макроси на день: білки $avgProtein г, жири $avgFat г, " +
                    "вуглеводи $avgCarbs г."
            )
            state.latestWeight?.let { w ->
                val delta = state.weightDelta
                val trend = when {
                    delta == null -> ""
                    delta > 0 -> " (зросла на ${"%.1f".format(delta)} кг за період)"
                    delta < 0 -> " (знизилась на ${"%.1f".format(-delta)} кг за період)"
                    else -> ""
                }
                appendLine("Поточна вага: ${"%.1f".format(w)} кг$trend.")
            }
        }.trim()
    }

    /**
     * Зберігає вагу за сьогодні та оновлює вагу в профілі, щоб норма калорій
     * лишалась актуальною.
     */
    fun addWeight(value: String) {
        val weight = value.replace(',', '.').toDoubleOrNull() ?: return
        if (weight !in 20.0..400.0) return
        viewModelScope.launch {
            weightRepository.add(LocalDate.now(), weight)
            profileRepository.getProfile()?.let { profile ->
                profileRepository.save(profile.copy(weightKg = weight))
            }
        }
    }
}
