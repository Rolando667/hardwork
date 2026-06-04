package com.calorieai.app.ui.diary

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.calorieai.app.data.repository.DiaryRepository
import com.calorieai.app.data.repository.ProfileRepository
import com.calorieai.app.domain.NutritionCalculator
import com.calorieai.app.domain.NutritionTargets
import com.calorieai.app.domain.model.FoodEntry
import com.calorieai.app.domain.model.MealType
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

/** Страва/прийом їжі: кілька компонентів зі спільним groupId. */
data class DiaryMeal(
    val groupId: String,
    val mealType: MealType,
    val createdAt: Long,
    val items: List<FoodEntry>
) {
    val totalKcal: Int get() = items.sumOf { it.kcal }
    val totalProtein: Double get() = items.sumOf { it.protein }
    val totalFat: Double get() = items.sumOf { it.fat }
    val totalCarbs: Double get() = items.sumOf { it.carbs }
    val totalGrams: Int get() = items.sumOf { it.grams }
}

data class DiaryUiState(
    val date: LocalDate = LocalDate.now(),
    val meals: List<DiaryMeal> = emptyList(),
    val filter: MealType? = null,
    val hasAnyEntries: Boolean = false,
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
    private val filter = MutableStateFlow<MealType?>(null)
    private var lastDeleted: List<FoodEntry> = emptyList()

    private val entriesFlow = selectedDate.flatMapLatest { date ->
        diaryRepository.observeEntriesForDate(date)
    }

    val uiState: StateFlow<DiaryUiState> = combine(
        selectedDate,
        profileRepository.observeProfile(),
        entriesFlow,
        filter
    ) { date, profile, entries, activeFilter ->
        val targets = profile?.takeIf { it.isComplete }?.let { NutritionCalculator.targets(it) }

        // Групуємо записи у страви; впорядковуємо від ранніх до пізніх.
        val allMeals = entries
            .groupBy { it.mealGroupId.ifEmpty { "single_${it.id}" } }
            .map { (groupId, items) ->
                DiaryMeal(
                    groupId = groupId,
                    mealType = items.first().mealType,
                    createdAt = items.minOf { it.createdAt },
                    items = items
                )
            }
            .sortedBy { it.createdAt }

        val visibleMeals =
            if (activeFilter == null) allMeals else allMeals.filter { it.mealType == activeFilter }

        DiaryUiState(
            date = date,
            meals = visibleMeals,
            filter = activeFilter,
            hasAnyEntries = entries.isNotEmpty(),
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

    fun setFilter(mealType: MealType?) {
        filter.value = mealType
    }

    fun updateEntry(entry: FoodEntry) = viewModelScope.launch {
        diaryRepository.update(entry)
    }

    fun deleteEntry(entry: FoodEntry) = viewModelScope.launch {
        lastDeleted = listOf(entry)
        diaryRepository.delete(entry)
    }

    fun deleteMeal(meal: DiaryMeal) = viewModelScope.launch {
        lastDeleted = meal.items
        diaryRepository.deleteGroup(meal.groupId)
    }

    fun undoDelete() = viewModelScope.launch {
        if (lastDeleted.isNotEmpty()) {
            diaryRepository.addEntries(lastDeleted)
            lastDeleted = emptyList()
        }
    }
}
