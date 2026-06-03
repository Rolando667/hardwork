package com.calorieai.app.data.local

import androidx.room.TypeConverter
import com.calorieai.app.domain.model.ActivityLevel
import com.calorieai.app.domain.model.EntrySource
import com.calorieai.app.domain.model.Goal
import com.calorieai.app.domain.model.Sex
import java.time.LocalDate

/** Конвертери типів для Room (enum'и зберігаються як назви, дата — як ISO-рядок). */
class Converters {
    @TypeConverter
    fun fromLocalDate(date: LocalDate?): String? = date?.toString()

    @TypeConverter
    fun toLocalDate(value: String?): LocalDate? = value?.let(LocalDate::parse)

    @TypeConverter
    fun fromSex(sex: Sex): String = sex.name

    @TypeConverter
    fun toSex(value: String): Sex = Sex.valueOf(value)

    @TypeConverter
    fun fromActivityLevel(level: ActivityLevel): String = level.name

    @TypeConverter
    fun toActivityLevel(value: String): ActivityLevel = ActivityLevel.valueOf(value)

    @TypeConverter
    fun fromGoal(goal: Goal): String = goal.name

    @TypeConverter
    fun toGoal(value: String): Goal = Goal.valueOf(value)

    @TypeConverter
    fun fromEntrySource(source: EntrySource): String = source.name

    @TypeConverter
    fun toEntrySource(value: String): EntrySource = EntrySource.valueOf(value)
}
