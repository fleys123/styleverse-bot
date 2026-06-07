import asyncio
import json
import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

import ai_service
import database
import storage

load_dotenv()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

STATE_IDLE = "idle"
STATE_WAITING_PROFILE = "waiting_profile"
STATE_WAITING_SCENE = "waiting_scene"
STATE_TRAINING_COLLECTING = "training_collecting"
STATE_WAITING_REVIEW = "waiting_review"

MIN_TRAINING_PHOTOS = 5
MAX_TRAINING_PHOTOS = 15

BACK_BTN = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 В меню", callback_data="menu")]])

CHANNEL = "@StyleVerse_gallery"

RESULT_BTNS = InlineKeyboardMarkup([
    [InlineKeyboardButton("📤 Поделиться в канал", callback_data="share_channel")],
    [InlineKeyboardButton("🔙 В меню", callback_data="menu")],
])

PREVIEWS_DIR = Path(__file__).parent / "previews"
PREVIEW_IDS_FILE = PREVIEWS_DIR / "file_ids.json"
_preview_ids: dict = {}


def _load_preview_ids():
    global _preview_ids
    if PREVIEW_IDS_FILE.exists():
        try:
            _preview_ids = json.loads(PREVIEW_IDS_FILE.read_text())
        except Exception:
            _preview_ids = {}


def _save_preview_id(filename: str, file_id: str):
    _preview_ids[filename] = file_id
    try:
        PREVIEW_IDS_FILE.write_text(json.dumps(_preview_ids))
    except Exception:
        pass

# Индексы пресетов у которых есть превью → имя файла
PRESET_PREVIEWS = {
    0:  "01_chb_kino.jpg",
    1:  "02_portret.jpg",
    2:  "03_candid_iphone.jpg",
    3:  "04_fashion.jpg",
    4:  "05_bougainvillea.jpg",
    5:  "06_peonies.jpg",
    6:  "07_desert.jpg",
    7:  "08_butterflies.jpg",
    8:  "09_lilac.jpg",
    9:  "10_horse.jpg",
    10: "11_ghostface.jpg",
}

# Превью для онбординга новых пользователей (3 лучших)
ONBOARDING_PREVIEWS = ["01_chb_kino.jpg", "05_bougainvillea.jpg", "06_peonies.jpg"]

SCENE_PRESETS = [
    ("🖤 Чёрно-белое кино",
     "Used uploaded photo, don't change a face, don't distort and keep the face exactly as in the uploaded photo and create a candid snapshot captured on a low-quality disposable camera. "
     "Photo-realistic close-up shot, only macro face shot, black and white, full voluminous hair, hair slightly blown by the wind falling across the face, "
     "chin slightly raised, dreamy gaze, eyes closed, and she is smiling, voluminous white dress, squatting on wet textured seaside rocks. "
     "The background features a dramatic large coastal cliff face under a heavily misty, overcast and moody grey sky. "
     "The lighting is diffused and natural. The overall atmosphere is cinematic and raw. "
     "Cinematic photo taken on a film camera 85mm. 9:16 format."),

    ("💫 Портрет",
     "Used uploaded photo, don't change a face, keep the face exactly as in the uploaded photo. "
     "Close-up portrait with focus on the right eye, nose and lips. Head slightly tilted to the left. "
     "Right eye open looking directly at the camera, eye color same as in the photo, long defined lashes. "
     "Thin strands of wet hair on forehead and cheek. High-contrast lighting, strong warm light source from the right "
     "casting sharp shadow covering the left side of face including left eye and part of nose. "
     "Smooth natural skin texture. Full glossy lips, natural pinkish-brown color. "
     "Warm color palette, natural skin tones, laminated brows. "
     "Intense and captivating mood, hyper-realistic photography style. 9:16 format."),

    ("📱 Кандид на iPhone",
     "Used uploaded photo, don't change a face, keep the face exactly as in the uploaded photo. "
     "Realistic candid snapshot on iPhone 15 Pro. Bright sunny day, high quality, live moment effect. "
     "Photo looks spontaneous. Slight digital grain, natural sun glare, soft shadows. No studio look. 9:16 format."),

    ("🌟 Fashion съёмка",
     "Used uploaded photo, don't change a face, keep the face exactly as in the uploaded photo. "
     "High-end editorial fashion photoshoot. Professional studio lighting, clean neutral beige background. "
     "Vogue magazine aesthetic, elegant pose, stylish outfit. "
     "Sharp details, professional model look, luxury fashion campaign quality. 9:16 format."),

    ("🌺 У стены под цветами",
     "Used uploaded photo, don't change a face, keep the face exactly as in the uploaded photo. "
     "Photo-realistic portrait. Girl standing near a warm terracotta Mediterranean wall covered "
     "with bright orange-pink bougainvillea flowers in full bloom. Casual elegant outfit. "
     "Warm natural sunlight, soft shadows, dreamy summer atmosphere. "
     "Cinematic quality, shallow depth of field. 9:16 format."),

    ("🌸 Среди белых пионов",
     "Used uploaded photo, don't change a face, keep the face exactly as in the uploaded photo. "
     "Tender close-up portrait. Girl sitting among large white blooming peonies surrounding her. "
     "Soft diffused light, pastel tones, gentle spring romantic atmosphere. "
     "Dreamy and airy mood, shallow depth of field, natural beauty. 9:16 format."),

    ("🏜️ В песках на закате",
     "Used uploaded photo, don't change a face, keep the face exactly as in the uploaded photo. "
     "High-fashion editorial shot. Girl lying or sitting on smooth golden sand dunes at sunset. "
     "Black elegant outfit, warm glowing sunset light from the horizon, long shadows. "
     "Cinematic and dramatic atmosphere, luxury fashion campaign quality. 9:16 format."),

    ("🦋 Портрет с бабочками",
     "Used uploaded photo, don't change a face, keep the face exactly as in the uploaded photo. "
     "Magical close-up portrait. White butterflies sitting on the girl's face and hands. "
     "Warm golden light streaming through window blinds creating soft stripes of light and shadow. "
     "Dreamy, ethereal and enchanting mood, hyper-realistic photography style. 9:16 format."),

    ("🌿 В саду среди сирени",
     "Used uploaded photo, don't change a face, keep the face exactly as in the uploaded photo. "
     "Spring portrait in a blooming lilac garden. Girl surrounded by purple and white lilac flowers "
     "with soft natural bokeh background. Warm golden hour light, gentle and romantic atmosphere. "
     "Pinterest aesthetic, soft skin tones, dreamy depth of field. 9:16 format."),

    ("🐎 В горах на лошади",
     "Used uploaded photo, don't change a face, keep the face exactly as in the uploaded photo. "
     "Cinematic shot of a girl sitting on a black horse in a lush green mountain valley. "
     "Dramatic Caucasus mountain landscape, moody clouds, cinematic color grading. "
     "Epic and powerful composition, natural lighting, high-end adventure fashion aesthetic. 9:16 format."),

    ("👻 Очень страшное кино",
     "Used uploaded photo, don't change a face, keep the face exactly as in the uploaded photo. "
     "Photo-realistic selfie 3:4. "
     "Girl with even glowing skin, soft dusty-pink blush, light wet highlighter on cheekbones, glossy lips with nude contour slightly darker than the gloss, mouth slightly open. "
     "Shiny hair with visible texture, slightly messy and wet, strands falling on face from both sides. "
     "Long square nails, bordeaux glossy finish. Thin gold chain on neck. "
     "Shot on iPhone 17 Pro front camera (phone not visible), nighttime, completely dark room, no flash. "
     "Only light source — red neon strip on the wall reflecting red highlights on skin, body and hair. "
     "Slight imperfection of the shot, accidental live moment effect, high quality, high texture detail, realism. "
     "Dark room background, large red neon strip on wall in casual waves. "
     "Girl wearing black synthetic top with lace trim. "
     "Behind her close — a person in full black outfit, black fabric gloves, Ghostface mask from Scream movie. "
     "His hand rests on her head with strands of hair on her face, other hand on her shoulder. "
     "Girl's face slightly turned sideways, finger near mouth. "
     "High resolution, cinematic grain, natural skin texture with visible pores and light glow on raised areas. "
     "No heavy HDR or full face retouching. High detail of face, clothing, lace, neon strip, mask, gloves. "
     "Looks like a candid live selfie. Face exactly as in the reference photo. 9:16 format."),
]


def main_menu_keyboard(has_photo: bool, has_lora: bool = False) -> InlineKeyboardMarkup:
    if has_photo:
        buttons = [
            [InlineKeyboardButton("✨ Создать фото по шаблону", callback_data="scene")],
            [InlineKeyboardButton("🔄 Обновить своё фото", callback_data="update_photo")],
        ]
    else:
        buttons = [[InlineKeyboardButton("📸 Загрузить своё фото", callback_data="update_photo")]]
    buttons.append([InlineKeyboardButton("💬 Тех поддержка", url="https://t.me/Fleys2")])
    return InlineKeyboardMarkup(buttons)


def training_keyboard(photo_count: int) -> InlineKeyboardMarkup:
    buttons = []
    if photo_count >= MIN_TRAINING_PHOTOS:
        buttons.append([InlineKeyboardButton(
            f"🚀 Начать обучение ({photo_count} фото)", callback_data="train_start"
        )])
    buttons.append([InlineKeyboardButton("🔙 В меню", callback_data="menu")])
    return InlineKeyboardMarkup(buttons)


def scene_preset_keyboard() -> InlineKeyboardMarkup:
    buttons = []
    row = []
    for i, (label, _) in enumerate(SCENE_PRESETS):
        row.append(InlineKeyboardButton(label, callback_data=f"sp_{i}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton("✏️ Написать своё описание", callback_data="sp_custom")])
    buttons.append([InlineKeyboardButton("🔙 В меню", callback_data="menu")])
    return InlineKeyboardMarkup(buttons)


# ─── Commands ────────────────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    database.register_user(user_id, user.username, user.full_name)

    if database.is_banned(user_id):
        await update.message.reply_text("🚫 Доступ заблокирован.")
        return

    context.user_data["state"] = STATE_IDLE
    has_photo = storage.has_profile_photo(user_id)

    if has_photo:
        has_lora = storage.has_user_lora(user_id)
        await update.message.reply_text(
            "✨ С возвращением в StyleVerse!\n\nВыбери что хочешь сделать:",
            reply_markup=main_menu_keyboard(True, has_lora)
        )
        return

    # Показываем примеры результатов
    preview_media = []
    for i, fname in enumerate(ONBOARDING_PREVIEWS):
        path = PREVIEWS_DIR / fname
        if path.exists():
            caption = "✨ Смотри что получается 👇" if i == 0 else ""
            preview_media.append(InputMediaPhoto(open(path, "rb"), caption=caption))
    if preview_media:
        await update.message.reply_media_group(media=preview_media)

    await update.message.reply_text(
        "✨ StyleVerse — нейросеть создаст крутые фото с тобой\n\n"
        "Как это работает:\n\n"
        "1. 📸 Загружаешь своё фото\n"
        "2. ✨ Выбираешь шаблон — чёрно-белое кино, пионы, бабочки и другие\n"
        "3. ✏️ Или описываешь своё — хоть яхта в Монако, хоть крыша в Токио\n"
        "4. 🤖 Нейросеть создаёт твоё фото за 30 секунд\n\n"
        "Для лучшего результата:\n"
        "• Фото анфас, лицо чёткое\n"
        "• Хорошее освещение\n"
        "• Ты один/одна в кадре",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📸 Попробовать бесплатно", callback_data="update_photo")]
        ])
    )



async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 СПРАВКА — StyleVerse\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "🔘 КНОПКИ МЕНЮ:\n"
        "━━━━━━━━━━━━━━━━\n\n"
        "📸 Загрузить / обновить фото\n"
        "Загружает твоё фото в память бота. "
        "Лучший результат: портрет с чётким лицом, хорошее освещение, без других людей.\n\n"
        "🌍 Вставить себя в сцену\n"
        "Выбери готовую локацию или напиши своё описание — "
        "бот создаст реалистичное фото где ты в этом месте. "
        "Можно писать на русском или английском.\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "💡 СОВЕТЫ:\n"
        "━━━━━━━━━━━━━━━━\n\n"
        "• Фото лица должно быть чётким — это главное для качества\n"
        "• Описывай сцену детально: не просто 'пляж', а 'пляж на Майорке с бирюзовой водой'\n"
        "• Если результат не понравился — попробуй ещё раз, каждый раз разный\n\n"
        "/start — главное меню\n"
        "/help — эта справка"
    )


# ─── Callbacks ───────────────────────────────────────────────────────────────

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id

    if query.data == "menu":
        context.user_data["state"] = STATE_IDLE
        has_photo = storage.has_profile_photo(user_id)
        has_lora = storage.has_user_lora(user_id)
        kb = main_menu_keyboard(has_photo, has_lora)
        try:
            await query.edit_message_text("Выбери действие:", reply_markup=kb)
        except Exception:
            await query.message.reply_text("Выбери действие:", reply_markup=kb)

    elif query.data == "share_channel":
        result_url = context.user_data.get("last_result_url")
        if not result_url:
            await query.answer("Нет результата для публикации.", show_alert=True)
            return
        context.user_data["state"] = STATE_WAITING_REVIEW
        await query.edit_message_text(
            "✍️ Напиши свой отзыв — мы опубликуем его вместе с фото в канале.\n\n"
            "Например: «Результат просто огонь, я в восторге!»"
        )

    elif query.data == "update_photo":
        context.user_data["state"] = STATE_WAITING_PROFILE
        await query.edit_message_text(
            "📸 Пришли своё фото\n\n"
            "✅ Подойдёт:\n"
            "• Портрет — лицо занимает бо́льшую часть кадра\n"
            "• Чёткое изображение, хорошее освещение\n"
            "• Один человек в кадре\n"
            "• Анфас или лёгкий поворот\n\n"
            "❌ Не подойдёт:\n"
            "• Групповое фото\n"
            "• Лицо маленькое или далеко\n"
            "• Тёмное, размытое или сделанное в профиль\n"
            "• Солнечные очки, маска, капюшон закрывает лицо\n\n"
            "Чем лучше исходное фото — тем реалистичнее результат 👇"
        )

    elif query.data.startswith("receipt_"):
        uid = int(query.data.split("_")[1])
        user = update.effective_user
        name = f"@{user.username}" if user.username else user.full_name
        await query.answer("Запрос отправлен, чек пришлём в ближайшее время.", show_alert=True)
        try:
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=(
                    f"🧾 Запрос чека об оплате\n\n"
                    f"👤 {name}\n"
                    f"🆔 ID: {uid}\n"
                    f"💳 Сумма: 799 ₽\n\n"
                    f"Выбей чек в «Мой налог» и отправь пользователю."
                ),
            )
        except Exception:
            pass

    elif query.data == "buy_sub":
        import payment as pay_module
        try:
            return_url = f"https://t.me/{context.bot.username}"
            payment_id, pay_url = pay_module.create_payment(user_id, return_url)
            await query.edit_message_text(
                "💳 Оплата подписки StyleVerse\n\n"
                "20 генераций на 30 дней — 799 ₽\n\n"
                "Нажми кнопку ниже чтобы перейти к оплате.\n"
                "После оплаты подписка активируется автоматически.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("💳 Оплатить 799 ₽", url=pay_url)],
                    [InlineKeyboardButton("🔙 В меню", callback_data="menu")],
                ]),
            )
        except Exception as e:
            logger.error(f"Payment creation failed for {user_id}: {e}")
            await query.edit_message_text(
                "❌ Не удалось создать платёж. Попробуйте позже или напишите в поддержку: @Fleys2",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 В меню", callback_data="menu")]]),
            )

    elif query.data == "scene":
        if not storage.has_profile_photo(user_id):
            try:
                await query.edit_message_text("Сначала загрузи своё фото!", reply_markup=main_menu_keyboard(False))
            except Exception:
                await query.message.reply_text("Сначала загрузи своё фото!", reply_markup=main_menu_keyboard(False))
            return
        try:
            await query.edit_message_text(
                "✨ Выбери шаблон или напиши своё описание:",
                reply_markup=scene_preset_keyboard(),
            )
        except Exception:
            try:
                await query.message.delete()
            except Exception:
                pass
            await query.message.reply_text(
                "✨ Выбери шаблон или напиши своё описание:",
                reply_markup=scene_preset_keyboard(),
            )

    elif query.data == "train_lora":
        if not storage.has_profile_photo(user_id):
            await query.edit_message_text(
                "Сначала загрузи своё фото!", reply_markup=main_menu_keyboard(False)
            )
            return
        context.user_data["state"] = STATE_TRAINING_COLLECTING
        context.user_data["training_photos"] = []
        await query.edit_message_text(
            "🧠 СОЗДАНИЕ AI-АВАТАРА\n\n"
            "Загрузи 5–15 своих фотографий. Чем больше — тем лучше результат.\n\n"
            "📌 Требования к фото:\n"
            "• Разные ракурсы лица (анфас, профиль, 3/4)\n"
            "• Разное освещение и фон\n"
            "• Лицо чёткое, не размытое\n"
            "• Без солнечных очков\n"
            "• Только ты, без других людей\n\n"
            "⏳ Обучение займёт ~10–15 минут. Я напишу когда будет готово.\n\n"
            "Начинай присылать фото 👇",
            reply_markup=training_keyboard(0),
        )

    elif query.data == "train_start":
        photos = context.user_data.get("training_photos", [])
        if len(photos) < MIN_TRAINING_PHOTOS:
            await query.answer(f"Нужно минимум {MIN_TRAINING_PHOTOS} фото!", show_alert=True)
            return
        context.user_data["state"] = STATE_IDLE
        status_msg = await query.edit_message_text(
            f"⏳ Начинаю обучение на {len(photos)} фото...\n"
            "Это займёт 10–15 минут. Можешь пока закрыть бот — я напишу когда готово."
        )
        asyncio.create_task(_start_training(update, context, photos, status_msg))

    elif query.data.startswith("sp_gen_"):
        idx = int(query.data[7:])
        label, scene_prompt = SCENE_PRESETS[idx]
        context.user_data["state"] = STATE_IDLE
        try:
            await query.message.delete()
        except Exception:
            pass
        status_msg = await query.message.reply_text(f"⏳ Генерирую: {label}...")
        await _generate_scene(update, context, scene_prompt, status_msg, label)

    elif query.data.startswith("sp_"):
        idx = query.data[3:]
        if idx == "custom":
            context.user_data["state"] = STATE_WAITING_SCENE
            await query.edit_message_text(
                "✏️ Напиши описание сцены:\n\n"
                "Например: 'в кафе в Париже утром' или 'на яхте в Средиземном море'"
            )
        else:
            idx_int = int(idx)
            label, scene_prompt = SCENE_PRESETS[idx_int]
            preview_file = PRESET_PREVIEWS.get(idx_int)
            preview_path = PREVIEWS_DIR / preview_file if preview_file else None

            if preview_path and preview_path.exists():
                cached_id = _preview_ids.get(preview_file)
                msg = await query.message.reply_photo(
                    photo=cached_id if cached_id else open(preview_path, "rb"),
                    caption=f"{label}\n\nПолучится примерно вот так ✨",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("✨ Сгенерировать", callback_data=f"sp_gen_{idx_int}")],
                        [InlineKeyboardButton("🔙 Назад", callback_data="scene")],
                    ]),
                )
                if not cached_id:
                    _save_preview_id(preview_file, msg.photo[-1].file_id)
                try:
                    await query.message.delete()
                except Exception:
                    pass
            else:
                context.user_data["state"] = STATE_IDLE
                status_msg = await query.edit_message_text(f"⏳ Генерирую: {label}...")
                await _generate_scene(update, context, scene_prompt, status_msg, label)


# ─── Photo handler ────────────────────────────────────────────────────────────

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    state = context.user_data.get("state", STATE_IDLE)
    if state == STATE_TRAINING_COLLECTING:
        await _collect_training_photo(update, context)
    elif state == STATE_WAITING_PROFILE:
        await _save_profile_photo(update, context)
    else:
        context.user_data["state"] = STATE_WAITING_PROFILE
        await _save_profile_photo(update, context)


async def _collect_training_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    photos = context.user_data.setdefault("training_photos", [])

    if len(photos) >= MAX_TRAINING_PHOTOS:
        await update.message.reply_text(
            f"Уже набрано максимум {MAX_TRAINING_PHOTOS} фото. Нажми «Начать обучение».",
            reply_markup=training_keyboard(len(photos)),
        )
        return

    photo = update.message.photo[-1]
    file = await photo.get_file()
    photo_path = storage.get_temp_dir() / f"{user_id}_train_{len(photos)}.jpg"
    await file.download_to_drive(str(photo_path))
    photos.append(str(photo_path))

    count = len(photos)
    if count < MIN_TRAINING_PHOTOS:
        remaining = MIN_TRAINING_PHOTOS - count
        text = f"✅ Фото {count} получено. Пришли ещё минимум {remaining}."
    else:
        text = f"✅ Фото {count} получено. Можешь прислать ещё или начать обучение."

    await update.message.reply_text(text, reply_markup=training_keyboard(count))


async def _save_profile_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    msg = await update.message.reply_text("⏳ Сохраняю фото...")

    photo = update.message.photo[-1]
    file = await photo.get_file()
    photo_path = storage.get_profile_photo_dir() / f"{user_id}.jpg"
    await file.download_to_drive(str(photo_path))
    storage.register_profile_photo(user_id, str(photo_path))
    context.user_data["state"] = STATE_IDLE
    has_lora = storage.has_user_lora(user_id)

    await msg.edit_text(
        "✅ Фото сохранено! Выбери что делать:",
        reply_markup=main_menu_keyboard(True, has_lora),
    )


async def _send_result(
    chat_id: int,
    context: ContextTypes.DEFAULT_TYPE,
    person_path: str,
    result_url: str,
    caption: str,
):
    context.user_data["last_result_url"] = result_url
    await context.bot.send_media_group(
        chat_id=chat_id,
        media=[
            InputMediaPhoto(open(person_path, "rb"), caption="До"),
            InputMediaPhoto(result_url, caption="После ✨"),
        ],
    )
    await context.bot.send_message(
        chat_id=chat_id,
        text=caption,
        reply_markup=RESULT_BTNS,
    )


# ─── Text handler ─────────────────────────────────────────────────────────────

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    state = context.user_data.get("state", STATE_IDLE)
    if state == STATE_WAITING_SCENE:
        scene_prompt = update.message.text
        status_msg = await update.message.reply_text("⏳ Генерирую изображение...")
        context.user_data["state"] = STATE_IDLE
        await _generate_scene(update, context, scene_prompt, status_msg, scene_prompt)
    elif state == STATE_WAITING_REVIEW:
        review = update.message.text.strip()
        result_url = context.user_data.get("last_result_url")
        context.user_data["state"] = STATE_IDLE
        if not result_url:
            await update.message.reply_text(
                "Фото не найдено, попробуй сгенерировать заново.",
                reply_markup=main_menu_keyboard(storage.has_profile_photo(update.effective_user.id)),
            )
            return
        try:
            await context.bot.send_photo(
                chat_id=CHANNEL,
                photo=result_url,
                caption=f"✨ {review}\n\n👉 @styleverse_bot",
            )
            await update.message.reply_text(
                "✅ Опубликовано в канале, спасибо!",
                reply_markup=main_menu_keyboard(True),
            )
        except Exception as e:
            logger.error(f"Channel post failed: {e}")
            await update.message.reply_text(
                "Ошибка публикации, попробуй позже.",
                reply_markup=main_menu_keyboard(True),
            )
    else:
        await update.message.reply_text("Используй /start чтобы начать.")


ADMIN_ID = 835360588

def _limit_message(reason: str) -> str:
    if reason == "free_limit":
        return (
            "✨ Вы использовали все 3 бесплатные генерации!\n\n"
            "Оформите подписку — 20 генераций в месяц всего за 799 ₽."
        )
    if reason == "sub_limit":
        return (
            "Вы использовали все 20 генераций за этот месяц.\n\n"
            "Подписка обновится в следующем месяце. "
            "Если хотите продлить раньше — оформите новую 👇"
        )
    if reason == "sub_expired":
        return "Срок вашей подписки истёк.\n\nОформите новую — 20 генераций за 799 ₽ 👇"
    return "Генерация недоступна. Напишите в поддержку."


def _limit_keyboard(reason: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💳 Оформить подписку — 799 ₽", callback_data="buy_sub")],
        [InlineKeyboardButton("🔙 В меню", callback_data="menu")],
    ])


async def _start_training(update, context, photo_paths: list, status_msg):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    try:
        lora_url, trigger_word = await ai_service.train_user_lora(photo_paths, user_id)
        storage.save_user_lora(user_id, lora_url, trigger_word)
        for path in photo_paths:
            try:
                Path(path).unlink()
            except Exception:
                pass
        await context.bot.send_message(
            chat_id=chat_id,
            text="🎉 AI-аватар готов! Теперь генерации будут значительно качественнее.\n\nВыбери сцену:",
            reply_markup=main_menu_keyboard(True, has_lora=True),
        )
    except Exception as e:
        logger.error(f"LoRA training failed for user {user_id}: {e}")
        await context.bot.send_message(
            chat_id=chat_id,
            text="❌ Ошибка обучения. Попробуй позже.",
            reply_markup=main_menu_keyboard(True, has_lora=False),
        )
        try:
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=f"🚨 Ошибка обучения LoRA\n\n👤 id={user_id}\n❗️ {str(e)}",
            )
        except Exception:
            pass


async def _generate_scene(update, context, scene_prompt: str, status_msg, label: str = ""):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    if context.user_data.get("generating"):
        await status_msg.edit_text("⏳ Подожди, идёт генерация...")
        return

    can_gen, reason = database.check_generation_access(user_id)
    if not can_gen:
        await status_msg.edit_text(_limit_message(reason), reply_markup=_limit_keyboard(reason))
        return

    person_path = storage.get_profile_photo_path(user_id)
    if not person_path:
        await status_msg.edit_text(
            "Фото не найдено. Пожалуйста, загрузите своё фото заново:",
            reply_markup=main_menu_keyboard(False),
        )
        return

    context.user_data["generating"] = True
    try:
        result_url = await ai_service.insert_into_scene(person_path, scene_prompt)
        database.increment_generation(user_id)
        await status_msg.delete()
        caption = f"✨ {label}" if label else "✨ Готово!"
        gen_status = database.get_generation_status(user_id)
        if gen_status:
            caption += f"\n\n📊 {gen_status}"
        await _send_result(chat_id, context, person_path, result_url, caption)
    except Exception as e:
        logger.error(f"Scene failed for user {user_id}: {e}")
        err_lower = str(e).lower()
        if "face" in err_lower or "no face" in err_lower or "detect" in err_lower:
            user_msg = (
                "😔 Не удалось распознать лицо на твоём фото.\n\n"
                "Попробуй загрузить другое фото:\n"
                "• Лицо чёткое и хорошо освещено\n"
                "• Занимает бо́льшую часть кадра\n"
                "• Без очков, маски или капюшона"
            )
        else:
            user_msg = "❌ Ошибка генерации. Повторите попытку через 1-5 минут."
        await status_msg.edit_text(user_msg, reply_markup=BACK_BTN)
        try:
            user = update.effective_user
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=(
                    f"🚨 Ошибка генерации\n\n"
                    f"👤 Пользователь: {user.full_name} (@{user.username}, id={user_id})\n"
                    f"🎬 Сцена: {scene_prompt}\n\n"
                    f"❗️ {str(e)}"
                ),
            )
        except Exception:
            pass
    finally:
        context.user_data["generating"] = False


# ─── Main ─────────────────────────────────────────────────────────────────────

def build_app() -> Application:
    _load_preview_ids()
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise ValueError("Укажи TELEGRAM_BOT_TOKEN в .env")

    app = (
        Application.builder()
        .token(token)
        .connect_timeout(30)
        .read_timeout(30)
        .write_timeout(30)
        .build()
    )
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    return app


if __name__ == "__main__":
    database.init_db()
    _load_preview_ids()
    build_app().run_polling()
