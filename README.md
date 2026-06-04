# Калорії AI — Android-додаток для підрахунку калорій

Сучасний Android-додаток (Kotlin + Jetpack Compose, Material 3) для підрахунку
калорій з AI-аналізом їжі за **текстом** та **фото** через Anthropic API.

> Інтерфейс повністю українською.

## Можливості

- **Профіль**: вік, стать, зріст, вага, рівень активності; розрахунок **BMR**
  (Mifflin-St Jeor) і **TDEE**; три цілі — підтримка / схуднення (−500) / набір (+500).
- **Щоденник**: страви за датою згруповані як **прийоми їжі** (Сніданок / Обід /
  Полуденок / Вечеря / Перекус). Кожна страва — одна картка із загальними КБЖУ;
  тап розкриває **деталізацію по компонентах** (з редагуванням/видаленням кожного).
  Фільтр історії: «Усі» (від ранніх до пізніх) або за конкретним прийомом їжі.
  Анімована **кругова діаграма** прогресу калорій і смужки Б/Ж/В, перемикач дат.
- **Додавання їжі двома способами**:
  - **Текстом** — список продуктів і грамовок;
  - **Фото** — камера (системний інтент + FileProvider) або галерея (Photo Picker);
    зображення надсилається до AI як base64.
- **AI-аналіз** через Anthropic Messages API (`claude-sonnet-4-20250514`):
  системний промт нутриціолога, відповідь у строгому JSON, парсинг через Moshi
  з обробкою «брудного» JSON та автоповтором.
- **Статистика**: екран із стовпчиковим графіком калорій за днями (тиждень/місяць),
  пунктирна лінія денної норми, середнє/максимум/кількість записаних днів, а також
  **лінійний графік динаміки ваги** з трендом (внесення ваги оновлює профіль і норму).
- **Нагадування пити воду**: періодичні сповіщення з налаштуванням частоти
  (кожні 1–4 год) через WorkManager; дозвіл на сповіщення запитується в застосунку.
  Опція **«Не нагадувати під час зустрічей»** читає синхронізований на телефоні
  Google Календар (дозвіл `READ_CALENDAR`, без входу через Google) і пропускає
  нагадування, коли саме зараз триває зустріч.
- **AI-ключ у застосунку**: ключ Anthropic вводиться прямо в Профілі та
  зберігається локально (DataStore) — не потрібно перезбирати APK.
- **Дизайн/UX**: Material 3 + динамічна тема (Material You) + ручний вибір
  світла/темна; скруглені картки, анімації, shimmer-завантаження, порожні стани,
  snackbar для помилок; нижня навігація (Щоденник / Додати / Статистика / Профіль).

## Архітектура

MVVM + Repository + Hilt DI, односпрямований потік (`StateFlow`).

```
domain/            моделі + NutritionCalculator (BMR/TDEE/цілі)
data/local/        Room: entities, DAO, AppDatabase, Converters
data/remote/       Retrofit Anthropic API, DTO, промти, JsonExtractor
data/repository/   Profile / Diary / FoodAnalysis / Settings
di/                Hilt-модулі (Database, Network)
ui/diary|add|profile  екрани + ViewModel'и
ui/components/     ProgressRing, MacroBars, FoodEntryCard, EmptyState, Shimmer…
ui/theme/          Color, Type, Shape, Theme (Material You)
util/              ImageUtils (base64), CameraFileProvider, DateUtils, Result
```

## Технології

Kotlin 2.0 · Jetpack Compose (Material 3) · Hilt · Room (KSP) · Retrofit +
OkHttp + Moshi · DataStore · Coil · CameraX-free (системний інтент + FileProvider).
minSdk 26, compile/target SDK 35.

## Налаштування

**AI-ключ — найпростіше прямо в застосунку:** відкрийте вкладку **Профіль →
AI-аналіз (Anthropic)** і вставте свій ключ `sk-ant-…`. Він зберігається лише на
пристрої, перезбирати APK не потрібно.

Альтернативно — «вшити» ключ у збірку:

1. Скопіюйте `local.properties.example` → `local.properties` і вкажіть:
   ```properties
   sdk.dir=/шлях/до/Android/sdk
   ANTHROPIC_API_KEY=sk-ant-...
   ```
   Ключ потрапляє у `BuildConfig.ANTHROPIC_API_KEY` під час збірки і **не
   комітиться** в git. Введений у застосунку ключ має пріоритет над цим.
2. Збірка:
   ```bash
   ./gradlew assembleDebug          # debug APK
   ./gradlew testDebugUnitTest      # юніт-тести (розрахунки + парсинг JSON)
   ```

Без `ANTHROPIC_API_KEY` додаток збирається й працює, але AI-функції повертають
помилку (показується у snackbar).

## Тести

- `NutritionCalculatorTest` — BMR/TDEE/цілі та розподіл макросів.
- `AnalysisParsingTest` — парсинг валідного та «брудного» JSON (markdown/проза).
