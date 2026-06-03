package com.calorieai.app.util

import android.content.Context
import android.net.Uri
import androidx.core.content.FileProvider
import java.io.File

/** Створення тимчасового файлу та content:// URI для зйомки фото камерою. */
object CameraFileProvider {

    /**
     * Створює порожній файл у кеші (images/) і повертає захищений URI через
     * FileProvider, який можна передати в ACTION_IMAGE_CAPTURE.
     */
    fun createImageUri(context: Context): Uri {
        val imagesDir = File(context.cacheDir, "images").apply { mkdirs() }
        val file = File.createTempFile("food_", ".jpg", imagesDir)
        val authority = "${context.packageName}.fileprovider"
        return FileProvider.getUriForFile(context, authority, file)
    }
}
