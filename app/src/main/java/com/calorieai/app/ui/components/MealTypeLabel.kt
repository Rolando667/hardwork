package com.calorieai.app.ui.components

import androidx.compose.runtime.Composable
import androidx.compose.ui.res.stringResource
import com.calorieai.app.R
import com.calorieai.app.domain.model.MealType

/** Локалізована назва прийому їжі. */
@Composable
fun mealTypeLabel(mealType: MealType): String = stringResource(
    when (mealType) {
        MealType.BREAKFAST -> R.string.meal_breakfast
        MealType.LUNCH -> R.string.meal_lunch
        MealType.AFTERNOON -> R.string.meal_afternoon
        MealType.DINNER -> R.string.meal_dinner
        MealType.SNACK -> R.string.meal_snack
    }
)
