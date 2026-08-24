Построй визуальный план на OUTPUT timeline. Смысл важнее эффектов.
Используй визуальные акценты в начале, при новой мысли, цифре, примере, доказательстве и CTA.
Не генерируй HTML или TypeScript. Выбирай только semantic intents и structured data.

Разрешены только следующие `intent`:
`subtitle`, `hook_text`, `b_roll`, `screen_recording`, `screenshot`, `logo`,
`text_accent`, `simple_zoom`, `transition`, `simple_transition`, `cta`,
`animated_stat`, `animated_counter`, `comparison`, `process_flow`, `timeline`,
`quote`, `code_animation`, `feature_list`, `product_feature`, `before_after`,
`callout`, `chart`, `diagram`, `complex_capcut_effect`, `beauty_adjustment`,
`manual_visual_fix`.

Для `b_roll`, `screen_recording`, `screenshot` и `logo` `asset_id` обязателен. Выбирай только
ID из `available_assets` context; не выдумывай пути, ID или external URL. Если подходящего asset
нет, не создавай media-backed item (он будет направлен в deterministic fallback/review).
Motion Canvas intents используют structured `data` и не требуют придуманного `asset_id`.
