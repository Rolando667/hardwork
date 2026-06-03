package com.calorieai.app.ui.add

import android.net.Uri
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.calorieai.app.R
import com.calorieai.app.data.repository.DiaryRepository
import com.calorieai.app.data.repository.FoodAnalysisRepository
import com.calorieai.app.domain.model.EntrySource
import com.calorieai.app.domain.model.FoodItem
import com.calorieai.app.util.OperationResult
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import java.time.LocalDate
import javax.inject.Inject

enum class AddTab { TEXT, PHOTO }

data class AddUiState(
    val tab: AddTab = AddTab.TEXT,
    val textInput: String = "",
    val photoUri: Uri? = null,
    val isLoading: Boolean = false,
    val results: List<FoodItem> = emptyList(),
    val note: String? = null,
    val source: EntrySource = EntrySource.TEXT,
    val errorRes: Int? = null,
    val savedEvent: Boolean = false
) {
    val totalKcal: Int get() = results.sumOf { it.kcal }
    val hasResults: Boolean get() = results.isNotEmpty()
}

@HiltViewModel
class AddViewModel @Inject constructor(
    private val analysisRepository: FoodAnalysisRepository,
    private val diaryRepository: DiaryRepository
) : ViewModel() {

    private val _state = MutableStateFlow(AddUiState())
    val state: StateFlow<AddUiState> = _state.asStateFlow()

    fun selectTab(tab: AddTab) = _state.update { it.copy(tab = tab) }

    fun onTextChange(value: String) = _state.update { it.copy(textInput = value) }

    fun analyzeText() {
        val text = _state.value.textInput.trim()
        if (text.isEmpty()) {
            _state.update { it.copy(errorRes = R.string.add_empty_text_error) }
            return
        }
        runAnalysis(EntrySource.TEXT) { analysisRepository.analyzeText(text) }
    }

    fun onPhotoCaptured(uri: Uri) {
        _state.update { it.copy(photoUri = uri, results = emptyList(), note = null) }
        runAnalysis(EntrySource.PHOTO) { analysisRepository.analyzePhoto(uri) }
    }

    private fun runAnalysis(
        source: EntrySource,
        block: suspend () -> OperationResult<com.calorieai.app.data.remote.dto.AnalysisResult>
    ) {
        viewModelScope.launch {
            _state.update { it.copy(isLoading = true, errorRes = null, source = source) }
            when (val result = block()) {
                is OperationResult.Success -> _state.update {
                    it.copy(
                        isLoading = false,
                        results = result.data.toFoodItems(),
                        note = result.data.note
                    )
                }
                is OperationResult.Error -> _state.update {
                    it.copy(isLoading = false, errorRes = result.errorRes)
                }
                OperationResult.Loading -> Unit
            }
        }
    }

    /** Оновлення однієї позиції результату (ручне коригування перед збереженням). */
    fun updateResult(index: Int, item: FoodItem) {
        _state.update { state ->
            val updated = state.results.toMutableList().also {
                if (index in it.indices) it[index] = item
            }
            state.copy(results = updated)
        }
    }

    fun removeResult(index: Int) {
        _state.update { state ->
            state.copy(results = state.results.filterIndexed { i, _ -> i != index })
        }
    }

    fun saveAll() {
        val current = _state.value
        if (current.results.isEmpty()) return
        viewModelScope.launch {
            diaryRepository.addItems(current.results, LocalDate.now(), current.source)
            _state.update {
                AddUiState(savedEvent = true)
            }
        }
    }

    fun clearResults() {
        _state.update { it.copy(results = emptyList(), note = null, photoUri = null) }
    }

    fun errorShown() = _state.update { it.copy(errorRes = null) }

    fun savedEventHandled() = _state.update { it.copy(savedEvent = false) }
}
