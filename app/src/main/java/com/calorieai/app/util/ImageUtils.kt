package com.calorieai.app.util

import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Matrix
import android.net.Uri
import android.util.Base64
import androidx.exifinterface.media.ExifInterface
import java.io.ByteArrayOutputStream
import kotlin.math.max

/** Результат підготовки зображення для Anthropic API. */
data class EncodedImage(
    val base64: String,
    val mediaType: String
)

object ImageUtils {

    private const val MAX_DIMENSION = 1280
    private const val JPEG_QUALITY = 80

    /**
     * Зчитує зображення за [uri], стискає до розумного розміру, виправляє
     * орієнтацію за EXIF і кодує у base64 (JPEG). Повертає null, якщо не вдалося
     * відкрити файл.
     */
    fun encodeForApi(context: Context, uri: Uri): EncodedImage? {
        val resolver = context.contentResolver

        val bitmap = resolver.openInputStream(uri)?.use { input ->
            BitmapFactory.decodeStream(input)
        } ?: return null

        val rotated = resolver.openInputStream(uri)?.use { input ->
            val exif = ExifInterface(input)
            applyExifRotation(bitmap, exif)
        } ?: bitmap

        val scaled = scaleDown(rotated, MAX_DIMENSION)

        val bytes = ByteArrayOutputStream().use { out ->
            scaled.compress(Bitmap.CompressFormat.JPEG, JPEG_QUALITY, out)
            out.toByteArray()
        }

        return EncodedImage(
            base64 = Base64.encodeToString(bytes, Base64.NO_WRAP),
            mediaType = "image/jpeg"
        )
    }

    private fun scaleDown(bitmap: Bitmap, maxDimension: Int): Bitmap {
        val largest = max(bitmap.width, bitmap.height)
        if (largest <= maxDimension) return bitmap
        val ratio = maxDimension.toFloat() / largest
        val width = (bitmap.width * ratio).toInt()
        val height = (bitmap.height * ratio).toInt()
        return Bitmap.createScaledBitmap(bitmap, width, height, true)
    }

    private fun applyExifRotation(bitmap: Bitmap, exif: ExifInterface): Bitmap {
        val orientation = exif.getAttributeInt(
            ExifInterface.TAG_ORIENTATION,
            ExifInterface.ORIENTATION_NORMAL
        )
        val matrix = Matrix()
        when (orientation) {
            ExifInterface.ORIENTATION_ROTATE_90 -> matrix.postRotate(90f)
            ExifInterface.ORIENTATION_ROTATE_180 -> matrix.postRotate(180f)
            ExifInterface.ORIENTATION_ROTATE_270 -> matrix.postRotate(270f)
            else -> return bitmap
        }
        return Bitmap.createBitmap(bitmap, 0, 0, bitmap.width, bitmap.height, matrix, true)
    }
}
