package com.calorieai.app.ui.diary

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.calorieai.app.data.repository.DiaryRepository
import com.calorieai.app.data.repository.ProfileRepository
import com.calorieai.app.domain.NutritionCalculator
import com.calorieai.app.domain.NutritionTargets
import com.calorieai.app.domain.model.FoodEntry
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.flatMapLatest
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch
import java.time.LocalDate
import javax.inject.Inject
import kotlin.math.roundToInt

data class DiaryUiState(
    val date: LocalDate = LocalDate.now(),
    val entries: List<FoodEntry> = emptyList(),
    val targets: NutritionTargets? = null,
    val profileComplete: Boolean = false,
    val consumedKcal: Int = 0,
    val consumedProtein: Int = 0,
    val consumedFat: Int = 0,
    val consumedCarbs: Int = 0
)

@OptIn(ExperimentalCoroutinesApi::class)
@HiltViewModel
class DiaryViewModel @Inject constructor(
    private val diaryRepository: DiaryRepository,
    profileRepository: ProfileRepository
) : ViewModel() {

    private val selectedDate = MutableStateFlow(LocalDate.now())
    private var lastDeleted: FoodEntry? = null

    private val entriesFlow = selectedDate.flatMapLatest { date ->
        diaryRepository.observeEntriesForDate(date)
    }

    val uiState: StateFlow<DiaryUiState> = combine(
        selectedDate,
        profileRepository.observeProfile(),
        entriesFlow
    ) { date, profile, entries ->
        val targets = profile?.takeIf { it.isComplete }?.let { NutritionCalculator.targets(it) }
        DiaryUiState(
            date = date,
            entries = entries,
            targets = targets,
            profileComplete = profile?.isComplete == true,
            consumedKcal = entries.sumOf { it.kcal },
            consumedProtein = entries.sumOf { it.protein }.roundToInt(),
            consumedFat = entries.sumOf { it.fat }.roundToInt(),
            consumedCarbs = entries.sumOf { it.carbs }.roundToInt()
        )
    }.stateIn(
        scope = viewModelScope,
        started = SharingStarted.WhileSubscribed(5_000),
        initialValue = DiaryUiState()
    )

    fun selectDate(date: LocalDate) {
        selectedDate.value = date
    }

    fun previousDay() {
        selectedDate.value = selectedDate.value.minusDays(1)
    }

    fun nextDay() {
        selectedDate.value = selectedDate.value.plusDays(1)
    }

    fun updateEntry(entry: FoodEntry) = viewModelScope.launch {
        diaryRepository.update(entry)
    }

    fun deleteEntry(entry: FoodEntry) = viewModelScope.launch {
        lastDeleted = entry
        diaryRepository.delete(entry)
    }

    fun undoDelete() = viewModelScope.launch {
        lastDeleted?.let { diaryRepository.add(it.copy(id = 0L)) }
        lastDeleted = null
    }
}
