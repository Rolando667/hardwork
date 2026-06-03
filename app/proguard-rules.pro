# Загальні правила оптимізації Android — у proguard-android-optimize.txt.

# Moshi: зберігаємо згенеровані адаптери та анотовані моделі.
-keep class com.squareup.moshi.** { *; }
-keep @com.squareup.moshi.JsonClass class * { *; }
-keepclassmembers class * {
    @com.squareup.moshi.FromJson <methods>;
    @com.squareup.moshi.ToJson <methods>;
}

# DTO-моделі додатка (серіалізація через Moshi).
-keep class com.calorieai.app.data.remote.dto.** { *; }

# Retrofit
-keepattributes Signature, InnerClasses, EnclosingMethod
-keepattributes RuntimeVisibleAnnotations, RuntimeVisibleParameterAnnotations
-dontwarn okhttp3.**
-dontwarn retrofit2.**
-dontwarn okio.**
