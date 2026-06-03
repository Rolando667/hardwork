package com.calorieai.app.util

/**
 * Проста обгортка результату операції з трьома станами.
 * [errorRes] — id рядкового ресурсу для показу у Snackbar (UI сам резолвить текст).
 */
sealed interface OperationResult<out T> {
    data object Loading : OperationResult<Nothing>
    data class Success<T>(val data: T) : OperationResult<T>
    data class Error(val errorRes: Int, val cause: Throwable? = null) :
        OperationResult<Nothing>
}
