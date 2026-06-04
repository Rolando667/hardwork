package com.calorieai.app.ui.profile

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.calorieai.app.R
import com.calorieai.app.data.repository.ProfileRepository
import com.calorieai.app.data.repository.SettingsRepository
import com.calorieai.app.domain.NutritionCalculator
import com.calorieai.app.domain.NutritionTargets
import com.calorieai.app.domain.model.ActivityLevel
import com.calorieai.app.domain.model.Goal
import com.calorieai.app.domain.model.Sex
import com.calorieai.app.domain.model.ThemeMode
import com.calorieai.app.domain.model.UserProfile
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import javax.inject.Inject

data class ProfileUiState(
    val age: String = "",
    val sex: Sex = Sex.MALE,
    val heightCm: String = "",
    val weightKg: String = "",
    val activityLevel: ActivityLevel = ActivityLevel.SEDENTARY,
    val goal: Goal = Goal.MAINTAIN,
    val themeMode: ThemeMode = ThemeMode.SYSTEM,
    val dynamicColor: Boolean = true,
    val apiKey: String = "",
    val waterReminderEnabled: Boolean = false,
    val waterIntervalHours: Int = 2,
    val skipDuringMeetings: Boolean = false,
    val targets: NutritionTargets? = null,
    val errorRes: Int? = null,
    val savedEvent: Boolean = false
)

@HiltViewModel
class ProfileViewModel @Inject constructor(
    private val profileRepository: ProfileRepository,
    private val settingsRepository: SettingsRepository
) : ViewModel() {

    private val _state = MutableStateFlow(ProfileUiState())
    val state: StateFlow<ProfileUiState> = _state.asStateFlow()

    init {
        viewModelScope.launch {
            profileRepository.getProfile()?.let { profile ->
                _state.update {
                    it.copy(
                        age = profile.age.toString(),
                        sex = profile.sex,
                        heightCm = profile.heightCm.toString(),
                        weightKg = trimDouble(profile.weightKg),
                        activityLevel = profile.activityLevel,
                        goal = profile.goal
                    )
                }
                recomputeTargets()
            }
        }
        // Ключ підвантажуємо один раз, щоб не перетирати поле під час набору.
        viewModelScope.launch {
            val initial = settingsRepository.settings.first()
            _state.update { it.copy(apiKey = initial.apiKey) }
        }
        viewModelScope.launch {
            settingsRepository.settings.collect { settings ->
                _state.update {
                    it.copy(
                        themeMode = settings.themeMode,
                        dynamicColor = settings.dynamicColor,
                        waterReminderEnabled = settings.waterReminderEnabled,
                        waterIntervalHours = settings.waterIntervalHours,
                        skipDuringMeetings = settings.skipDuringMeetings
                    )
                }
            }
        }
    }

    fun onApiKeyChange(value: String) {
        _state.update { it.copy(apiKey = value) }
        viewModelScope.launch { settingsRepository.setApiKey(value) }
    }

    fun onWaterReminderChange(enabled: Boolean) {
        _state.update { it.copy(waterReminderEnabled = enabled) }
        viewModelScope.launch { settingsRepository.setWaterReminderEnabled(enabled) }
    }

    fun onWaterIntervalChange(hours: Int) {
        _state.update { it.copy(waterIntervalHours = hours) }
        viewModelScope.launch { settingsRepository.setWaterIntervalHours(hours) }
    }

    fun onSkipDuringMeetingsChange(enabled: Boolean) {
        _state.update { it.copy(skipDuringMeetings = enabled) }
        viewModelScope.launch { settingsRepository.setSkipDuringMeetings(enabled) }
    }

    fun onAgeChange(value: String) = updateField { it.copy(age = value.filterDigits()) }
    fun onHeightChange(value: String) = updateField { it.copy(heightCm = value.filterDigits()) }
    fun onWeightChange(value: String) = updateField { it.copy(weightKg = value.filterDecimal()) }
    fun onSexChange(sex: Sex) = updateField { it.copy(sex = sex) }
    fun onActivityChange(level: ActivityLevel) = updateField { it.copy(activityLevel = level) }
    fun onGoalChange(goal: Goal) = updateField { it.copy(goal = goal) }

    private fun updateField(transform: (ProfileUiState) -> ProfileUiState) {
        _state.update(transform)
        recomputeTargets()
    }

    fun onThemeModeChange(mode: ThemeMode) {
        viewModelScope.launch { settingsRepository.setThemeMode(mode) }
    }

    fun onDynamicColorChange(enabled: Boolean) {
        viewModelScope.launch { settingsRepository.setDynamicColor(enabled) }
    }

    fun save() {
        val profile = currentProfile()
        if (profile == null || !profile.isComplete) {
            _state.update { it.copy(errorRes = R.string.profile_invalid) }
            return
        }
        viewModelScope.launch {
            profileRepository.save(profile)
            _state.update { it.copy(savedEvent = true) }
        }
    }

    fun errorShown() = _state.update { it.copy(errorRes = null) }
    fun savedEventHandled() = _state.update { it.copy(savedEvent = false) }

    private fun recomputeTargets() {
        val profile = currentProfile()
        val targets = profile?.takeIf { it.isComplete }?.let { NutritionCalculator.targets(it) }
        _state.update { it.copy(targets = targets) }
    }

    private fun currentProfile(): UserProfile? {
        val s = _state.value
        val age = s.age.toIntOrNull() ?: return null
        val height = s.heightCm.toIntOrNull() ?: return null
        val weight = s.weightKg.toDoubleOrNull() ?: return null
        return UserProfile(
            age = age,
            sex = s.sex,
            heightCm = height,
            weightKg = weight,
            activityLevel = s.activityLevel,
            goal = s.goal
        )
    }

    private fun trimDouble(value: Double): String =
        if (value % 1.0 == 0.0) value.toInt().toString() else value.toString()

    private fun String.filterDigits(): String = filter { it.isDigit() }.take(3)
    private fun String.filterDecimal(): String =
        filter { it.isDigit() || it == '.' }.take(6)
}
