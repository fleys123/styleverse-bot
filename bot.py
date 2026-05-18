import asyncio
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
import storage

load_dotenv()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

STATE_IDLE = "idle"
STATE_WAITING_PROFILE = "waiting_profile"
STATE_WAITING_GARMENT = "waiting_garment"
STATE_WAITING_CATEGORY = "waiting_category"
STATE_WAITING_SCENE = "waiting_scene"
STATE_COMBO_SCENE = "combo_scene"
STATE_TRAINING_COLLECTING = "training_collecting"

MIN_TRAINING_PHOTOS = 5
MAX_TRAINING_PHOTOS = 20

BACK_BTN = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 В меню", callback_data="menu")]])

RESULT_BTNS = InlineKeyboardMarkup([
    [InlineKeyboardButton("📤 Поделиться ботом", url="https://t.me/styleverse_bot")],
    [InlineKeyboardButton("🔙 В меню", callback_data="menu")],
])

SCENE_PRESETS = [
    ("🏖 Пляж Майами",       "on a beach in Miami, golden sunset light, warm breeze, candid moment, natural expression, shallow depth of field, 35mm film"),
    ("🗼 Токио ночью",        "in Tokyo at night, neon reflections on wet pavement, Shibuya crossing, candid street photography, natural pose, cinematic"),
    ("🏔 Снежные горы",       "in snowy mountains, dramatic peaks in background, soft natural light, candid photography, cozy winter atmosphere, Kodak Portra"),
    ("🎬 Красная дорожка",    "on a glamorous red carpet, photographers in background, soft studio lighting, elegant atmosphere, candid confident pose"),
    ("🌆 Нью-Йорк",          "in New York City, Manhattan streets, natural city light, candid urban photography, busy city life background, 35mm film"),
    ("🏙 Дубай",             "in Dubai at golden hour, luxury skyscrapers background, warm sunlight, candid travel photography, natural expression"),
    ("🌴 Тропический остров", "on a tropical island, turquoise water behind, soft natural light, candid vacation photo, relaxed natural pose, golden hour"),
    ("🌸 Японский сад",       "in a Japanese cherry blossom garden, sakura petals falling, soft diffused light, candid serene moment, film photography"),
]


def main_menu_keyboard(has_photo: bool, has_lora: bool = False) -> InlineKeyboardMarkup:
    if has_photo:
        lora_label = "🔄 Переобучить аватар ✅" if has_lora else "🧠 Обучить под себя"
        buttons = [
            [InlineKeyboardButton("👗 Примерить одежду", callback_data="tryon")],
            [InlineKeyboardButton("🌍 Вставить себя в сцену", callback_data="scene")],
            [InlineKeyboardButton("✨ Одежда + сцена вместе", callback_data="combo")],
            [InlineKeyboardButton(lora_label, callback_data="train_lora")],
            [InlineKeyboardButton("🔄 Обновить своё фото", callback_data="update_photo")],
        ]
    else:
        buttons = [[InlineKeyboardButton("📸 Загрузить своё фото", callback_data="update_photo")]]
    return InlineKeyboardMarkup(buttons)


def scene_preset_keyboard(mode: str) -> InlineKeyboardMarkup:
    buttons = []
    row = []
    for i, (label, _) in enumerate(SCENE_PRESETS):
        row.append(InlineKeyboardButton(label, callback_data=f"sp_{mode}_{i}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton("✏️ Написать своё описание", callback_data=f"sp_{mode}_custom")])
    buttons.append([InlineKeyboardButton("🔙 В меню", callback_data="menu")])
    return InlineKeyboardMarkup(buttons)


def category_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("👕 Верх", callback_data="cat_tops"),
            InlineKeyboardButton("👖 Низ", callback_data="cat_bottoms"),
        ],
        [InlineKeyboardButton("👗 Платье / комбинезон", callback_data="cat_one-pieces")],
        [InlineKeyboardButton("🔀 Определить автоматически", callback_data="cat_auto")],
    ])


# ─── Commands ────────────────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    context.user_data["state"] = STATE_IDLE
    has_photo = storage.has_profile_photo(user_id)

    if has_photo:
        await update.message.reply_text(
            "✨ С возвращением в StyleVerse!\n\n"
            "Выбери что хочешь сделать:",
            reply_markup=main_menu_keyboard(True, storage.has_user_lora(user_id))
        )
        return

    # First time — show full guide
    await update.message.reply_text(
        "👋 Привет! Я StyleVerse — AI-бот для работы с твоими фотографиями.\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "🤖 ЧТО Я УМЕЮ:\n"
        "━━━━━━━━━━━━━━━━\n\n"
        "👗 ПРИМЕРКА ОДЕЖДЫ\n"
        "Загружаешь фото одежды — я надеваю её на тебя. "
        "Не нужно идти в магазин, чтобы понять подойдёт ли вещь.\n\n"
        "🌍 ВСТАВКА В СЦЕНУ\n"
        "Выбираешь локацию из готового списка или описываешь своими словами — "
        "я помещаю тебя туда. Пляж в Майами, Токио ночью, красная дорожка — всё что угодно.\n\n"
        "✨ ОДЕЖДА + СЦЕНА ВМЕСТЕ\n"
        "Самая мощная функция: выбираешь одежду И локацию одновременно. "
        "Получаешь фото в новом образе в нужном месте.\n\n"
        "🧠 ПЕРСОНАЛЬНЫЙ АВАТАР\n"
        "Присылаешь 5-20 своих фото — бот обучает AI-модель под твою внешность. "
        "После этого все генерации точнее сохраняют твоё лицо. "
        "Обучение делается один раз и занимает ~5-10 минут.\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "📌 КАК НАЧАТЬ:\n"
        "━━━━━━━━━━━━━━━━\n\n"
        "1️⃣ Загрузи одно своё фото (лучше в полный рост)\n"
        "2️⃣ Выбери нужную функцию\n"
        "3️⃣ Следуй подсказкам бота\n"
        "4️⃣ Жди результат ~1-2 минуты\n\n"
        "💡 Для лучшего результата используй чёткое фото при хорошем освещении.\n\n"
        "⬇️ Нажми кнопку ниже чтобы загрузить своё фото и начать:",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📸 Загрузить своё фото", callback_data="update_photo")]
        ])
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 СПРАВКА — StyleVerse\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "🔘 КНОПКИ ГЛАВНОГО МЕНЮ:\n"
        "━━━━━━━━━━━━━━━━\n\n"
        "📸 Загрузить / обновить фото\n"
        "Загружает твоё фото в память бота. Именно это фото используется во всех функциях. "
        "Лучший результат: фото в полный рост, хорошее освещение, без лишних людей рядом.\n\n"
        "👗 Примерить одежду\n"
        "Пришли фото одежды → выбери тип (верх/низ/платье) → бот наденет её на тебя. "
        "Одежда лучше всего работает на белом фоне или на манекене.\n\n"
        "🌍 Вставить себя в сцену\n"
        "Напиши описание места — бот поместит тебя туда. "
        "Пиши конкретнее: не просто 'пляж', а 'пляж в Майами на закате'. "
        "Чем детальнее описание — тем лучше результат.\n\n"
        "✨ Одежда + сцена вместе\n"
        "Комбо-режим: пришли фото одежды → выбери тип → опиши сцену. "
        "Бот сначала наденет одежду, потом вставит тебя в нужное место. "
        "Занимает ~2 минуты, зато результат самый крутой.\n\n"
        "🧠 Обучить под себя\n"
        "Пришли 5-20 своих фото — бот обучит персональную AI-модель под твою внешность. "
        "Обучение занимает ~5-10 минут и делается один раз. "
        "После этого сцены и комбо-режим будут точнее сохранять твоё лицо.\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "💡 СОВЕТЫ:\n"
        "━━━━━━━━━━━━━━━━\n\n"
        "• Фото лица должно быть чётким — это влияет на качество\n"
        "• Для примерки лучше использовать одежду на белом фоне\n"
        "• Описывай сцену на русском или английском\n"
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
        kb = main_menu_keyboard(has_photo, storage.has_user_lora(user_id))
        try:
            await query.edit_message_text("Выбери действие:", reply_markup=kb)
        except Exception:
            await query.message.reply_text("Выбери действие:", reply_markup=kb)

    elif query.data == "update_photo":
        context.user_data["state"] = STATE_WAITING_PROFILE
        await query.edit_message_text(
            "📸 Пришли своё фото.\n\n"
            "Лучший результат: фото в полный рост или до пояса, хорошее освещение."
        )

    elif query.data == "tryon":
        if not storage.has_profile_photo(user_id):
            await query.edit_message_text(
                "Сначала загрузи своё фото!", reply_markup=main_menu_keyboard(False)
            )
            return
        context.user_data["state"] = STATE_WAITING_GARMENT
        context.user_data["combo"] = False
        await query.edit_message_text(
            "👗 Пришли фото одежды.\n\n"
            "Лучший результат: вещь на белом или сером фоне, либо на манекене."
        )

    elif query.data == "combo":
        if not storage.has_profile_photo(user_id):
            await query.edit_message_text(
                "Сначала загрузи своё фото!", reply_markup=main_menu_keyboard(False)
            )
            return
        context.user_data["state"] = STATE_WAITING_GARMENT
        context.user_data["combo"] = True
        await query.edit_message_text(
            "✨ Одежда + сцена!\n\n"
            "Шаг 1 из 2 — пришли фото одежды.\n"
            "Лучший результат: вещь на белом фоне или манекене."
        )

    elif query.data == "scene":
        if not storage.has_profile_photo(user_id):
            await query.edit_message_text(
                "Сначала загрузи своё фото!", reply_markup=main_menu_keyboard(False)
            )
            return
        await query.edit_message_text(
            "🌍 Выбери локацию или напиши своё описание:",
            reply_markup=scene_preset_keyboard("scene"),
        )

    elif query.data == "train_lora":
        context.user_data["state"] = STATE_TRAINING_COLLECTING
        context.user_data["training_photos"] = []
        await query.edit_message_text(
            "🧠 Обучение персонального аватара\n\n"
            "Пришли от 5 до 20 своих фотографий:\n"
            "• Разные ракурсы лица (фас, профиль, три четверти)\n"
            "• Хорошее освещение, без теней на лице\n"
            "• Разные позы и выражения\n"
            "• Без лишних людей на одном фото\n\n"
            "⏳ Обучение займёт ~5-10 минут — бот пришлёт уведомление когда готово.\n\n"
            "📸 Начинай присылать фото:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 В меню", callback_data="menu")],
            ]),
        )

    elif query.data == "start_training":
        photos = context.user_data.get("training_photos", [])
        if len(photos) < MIN_TRAINING_PHOTOS:
            await query.answer(f"Нужно минимум {MIN_TRAINING_PHOTOS} фото!", show_alert=True)
            return
        context.user_data["state"] = STATE_IDLE
        count = len(photos)
        await query.edit_message_text(
            f"🧠 Начинаю обучение на {count} фото...\n\n"
            "⏳ Это займёт ~5-10 минут. Я пришлю уведомление когда всё готово!\n\n"
            "Пока можешь пользоваться другими функциями бота."
        )
        asyncio.create_task(_run_training(update, context, photos))

    elif query.data.startswith("sp_"):
        _, mode, idx = query.data.split("_", 2)
        if idx == "custom":
            if mode == "scene":
                context.user_data["state"] = STATE_WAITING_SCENE
            else:
                context.user_data["state"] = STATE_COMBO_SCENE
            await query.edit_message_text(
                "✏️ Напиши описание сцены:\n\n"
                "Например: 'в кафе в Париже утром' или 'на яхте в Средиземном море'"
            )
        else:
            label, scene_prompt = SCENE_PRESETS[int(idx)]
            context.user_data["state"] = STATE_IDLE
            if mode == "scene":
                status_msg = await query.edit_message_text(
                    f"⏳ {label}...\nШаг 1: размещаю в сцене → Шаг 2: восстанавливаю лицо (~1-2 минуты)"
                )
                await _generate_scene(update, context, scene_prompt, status_msg)
            else:
                status_msg = await query.edit_message_text(
                    f"⏳ {label}...\nШаг 1: примерка → Шаг 2: сцена → Шаг 3: лицо (~2-3 минуты)"
                )
                await _generate_combo(update, context, scene_prompt, status_msg)

    elif query.data.startswith("cat_"):
        category = query.data[4:]  # "tops" | "bottoms" | "one-pieces" | "auto"
        garment_path = context.user_data.get("pending_garment")
        if not garment_path or not Path(garment_path).exists():
            await query.edit_message_text("Что-то пошло не так. Начни заново — /start")
            return
        context.user_data["pending_category"] = category

        if context.user_data.get("combo"):
            await query.edit_message_text(
                "✨ Шаг 2 из 2 — выбери сцену:",
                reply_markup=scene_preset_keyboard("combo"),
            )
        else:
            await query.edit_message_text("⏳ Генерирую примерку... (~30-60 секунд)")
            await _run_tryon(update, context, garment_path, category, edit_msg=query.message)


# ─── Photo handler ────────────────────────────────────────────────────────────

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    state = context.user_data.get("state", STATE_IDLE)

    if state == STATE_WAITING_PROFILE:
        await _save_profile_photo(update, context)
    elif state == STATE_WAITING_GARMENT:
        await _receive_garment(update, context)
    elif state == STATE_TRAINING_COLLECTING:
        await _collect_training_photo(update, context)
    else:
        context.user_data["state"] = STATE_WAITING_PROFILE
        await _save_profile_photo(update, context)


async def _save_profile_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    msg = await update.message.reply_text("⏳ Сохраняю фото...")

    photo = update.message.photo[-1]
    file = await photo.get_file()
    photo_path = storage.get_profile_photo_dir() / f"{user_id}.jpg"
    await file.download_to_drive(str(photo_path))
    storage.register_profile_photo(user_id, str(photo_path))
    context.user_data["state"] = STATE_IDLE

    await msg.edit_text(
        "✅ Фото сохранено! Выбери что делать:",
        reply_markup=main_menu_keyboard(True, storage.has_user_lora(user_id)),
    )


async def _receive_garment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    msg = await update.message.reply_text("⏳ Загружаю фото одежды...")

    photo = update.message.photo[-1]
    file = await photo.get_file()
    garment_path = storage.get_temp_dir() / f"{user_id}_garment.jpg"
    await file.download_to_drive(str(garment_path))

    context.user_data["pending_garment"] = str(garment_path)
    context.user_data["state"] = STATE_WAITING_CATEGORY

    await msg.edit_text(
        "Выбери тип одежды — это улучшает точность примерки:",
        reply_markup=category_keyboard(),
    )


async def _send_result(
    chat_id: int,
    context: ContextTypes.DEFAULT_TYPE,
    person_path: str,
    result_url: str,
    caption: str,
):
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


async def _run_tryon(update, context, garment_path: str, category: str, edit_msg=None):
    user_id = update.effective_user.id
    person_path = storage.get_profile_photo_path(user_id)
    context.user_data["state"] = STATE_IDLE
    context.user_data.pop("pending_garment", None)

    try:
        result_url = await ai_service.virtual_tryon(person_path, garment_path, category)
        if edit_msg:
            await edit_msg.delete()
        await _send_result(
            update.effective_chat.id, context, person_path,
            result_url, "✨ Вот как ты выглядишь в этой одежде!"
        )
    except Exception as e:
        logger.error(f"Try-on failed for user {user_id}: {e}")
        text = f"❌ Ошибка примерки. Попробуй другое фото одежды.\n\nДетали: {str(e)[:120]}"
        if edit_msg:
            await edit_msg.edit_text(text, reply_markup=BACK_BTN)
    finally:
        Path(garment_path).unlink(missing_ok=True)


async def _collect_training_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    photos: list = context.user_data.get("training_photos", [])

    if len(photos) >= MAX_TRAINING_PHOTOS:
        await update.message.reply_text(
            f"Уже набрано максимум ({MAX_TRAINING_PHOTOS}) фото. Нажми «Начать обучение».",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Начать обучение", callback_data="start_training")],
            ]),
        )
        return

    photo = update.message.photo[-1]
    file = await photo.get_file()
    photo_path = storage.get_temp_dir() / f"{user_id}_train_{len(photos)}.jpg"
    await file.download_to_drive(str(photo_path))

    photos.append(str(photo_path))
    context.user_data["training_photos"] = photos
    count = len(photos)

    if count < MIN_TRAINING_PHOTOS:
        await update.message.reply_text(
            f"📸 Фото {count} принято. Нужно ещё минимум {MIN_TRAINING_PHOTOS - count}.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 В меню", callback_data="menu")],
            ]),
        )
    else:
        await update.message.reply_text(
            f"📸 Фото {count} принято. Можешь прислать ещё или начать обучение.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Начать обучение", callback_data="start_training")],
                [InlineKeyboardButton("🔙 В меню", callback_data="menu")],
            ]),
        )


async def _run_training(update: Update, context: ContextTypes.DEFAULT_TYPE, photo_paths: list[str]):
    user_id = update.effective_user.id
    try:
        lora_url, trigger_word = await ai_service.train_user_lora(photo_paths, user_id)
        storage.save_user_lora(user_id, lora_url, trigger_word)
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=(
                "✅ Аватар обучен! Теперь при генерации сцен бот будет точнее "
                "сохранять твоё лицо и внешность.\n\n"
                "Выбери что делать:"
            ),
            reply_markup=main_menu_keyboard(True, has_lora=True),
        )
    except Exception as e:
        logger.error(f"LoRA training failed for user {user_id}: {e}")
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"❌ Ошибка обучения. Попробуй позже.\n\nДетали: {str(e)[:150]}",
        )
    finally:
        for path in photo_paths:
            Path(path).unlink(missing_ok=True)
        context.user_data.pop("training_photos", None)


# ─── Text handler ─────────────────────────────────────────────────────────────

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    state = context.user_data.get("state", STATE_IDLE)
    if state == STATE_WAITING_SCENE:
        scene_prompt = update.message.text
        status_msg = await update.message.reply_text(
            "⏳ Генерирую изображение...\n"
            "Шаг 1: размещаю в сцене → Шаг 2: восстанавливаю лицо (~1-2 минуты)"
        )
        context.user_data["state"] = STATE_IDLE
        await _generate_scene(update, context, scene_prompt, status_msg)
    elif state == STATE_COMBO_SCENE:
        scene_prompt = update.message.text
        status_msg = await update.message.reply_text(
            "⏳ Генерирую образ...\n"
            "Шаг 1: примерка → Шаг 2: сцена → Шаг 3: восстановление лица (~2-3 минуты)"
        )
        context.user_data["state"] = STATE_IDLE
        await _generate_combo(update, context, scene_prompt, status_msg)
    else:
        await update.message.reply_text("Используй /start чтобы начать.")


async def _generate_scene(update, context, scene_prompt: str, status_msg):
    user_id = update.effective_user.id
    person_path = storage.get_profile_photo_path(user_id)
    lora_data = storage.get_user_lora(user_id)
    chat_id = update.effective_chat.id

    try:
        if lora_data:
            result_url = await ai_service.insert_into_scene_lora(
                person_path, scene_prompt, lora_data["url"], lora_data["trigger"]
            )
        else:
            result_url = await ai_service.insert_into_scene(person_path, scene_prompt)
        await status_msg.delete()
        await _send_result(chat_id, context, person_path, result_url, f"✨ Ты в сцене: {scene_prompt}")
    except Exception as e:
        logger.error(f"Scene failed for user {user_id}: {e}")
        await status_msg.edit_text(
            f"❌ Ошибка генерации. Попробуй другую сцену.\n\nДетали: {str(e)[:120]}",
            reply_markup=BACK_BTN,
        )


async def _generate_combo(update, context, scene_prompt: str, status_msg):
    user_id = update.effective_user.id
    garment_path = context.user_data.get("pending_garment")
    category = context.user_data.get("pending_category", "auto")
    person_path = storage.get_profile_photo_path(user_id)
    lora_data = storage.get_user_lora(user_id)
    chat_id = update.effective_chat.id

    context.user_data.pop("pending_garment", None)
    context.user_data.pop("pending_category", None)
    context.user_data.pop("combo", None)

    try:
        if lora_data:
            result_url = await ai_service.tryon_in_scene_lora(
                person_path, garment_path, category, scene_prompt,
                lora_data["url"], lora_data["trigger"]
            )
        else:
            result_url = await ai_service.tryon_in_scene(
                person_path, garment_path, category, scene_prompt
            )
        await status_msg.delete()
        await _send_result(chat_id, context, person_path, result_url, f"✨ Твой образ: {scene_prompt}")
    except Exception as e:
        logger.error(f"Combo failed for user {user_id}: {e}")
        await status_msg.edit_text(
            f"❌ Ошибка генерации.\n\nДетали: {str(e)[:120]}",
            reply_markup=BACK_BTN,
        )
    finally:
        if garment_path and Path(garment_path).exists():
            Path(garment_path).unlink(missing_ok=True)


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
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

    logger.info("StyleVerse запущен. Ctrl+C для остановки.")
    app.run_polling()


if __name__ == "__main__":
    main()
