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
STATE_WAITING_SCENE = "waiting_scene"
STATE_TRAINING_COLLECTING = "training_collecting"

MIN_TRAINING_PHOTOS = 5
MAX_TRAINING_PHOTOS = 15

BACK_BTN = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 В меню", callback_data="menu")]])

RESULT_BTNS = InlineKeyboardMarkup([
    [InlineKeyboardButton("📤 Поделиться ботом", url="https://t.me/share/url?url=t.me/styleverse_bot&text=Попробуй этот AI-бот — вставляй себя в любые локации! 🔥")],
    [InlineKeyboardButton("🔙 В меню", callback_data="menu")],
])

SCENE_PRESETS = [
    ("🏖 Пляж Майами",       "on Miami beach at sunset, wearing a light linen shirt and shorts"),
    ("🗼 Токио ночью",        "in Tokyo at night, Shibuya crossing, wearing a stylish urban jacket and dark jeans"),
    ("🎬 Красная дорожка",    "on a red carpet event, wearing an elegant black suit"),
    ("🌆 Нью-Йорк",          "on a Manhattan street in New York City, wearing a casual coat and jeans"),
    ("🏙 Дубай",             "in Dubai with skyline view, wearing a smart casual white shirt and trousers"),
    ("🌴 Тропический остров", "on a tropical island beach, wearing a casual summer outfit"),
    ("🌸 Японский сад",       "in a Japanese cherry blossom garden, wearing a light casual outfit"),
]


def main_menu_keyboard(has_photo: bool, has_lora: bool = False) -> InlineKeyboardMarkup:
    if has_photo:
        buttons = [
            [InlineKeyboardButton("🌍 Вставить себя в сцену", callback_data="scene")],
            [InlineKeyboardButton("🔄 Обновить своё фото", callback_data="update_photo")],
        ]
    else:
        buttons = [[InlineKeyboardButton("📸 Загрузить своё фото", callback_data="update_photo")]]
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
    user_id = update.effective_user.id
    context.user_data["state"] = STATE_IDLE
    has_photo = storage.has_profile_photo(user_id)

    if has_photo:
        has_lora = storage.has_user_lora(user_id)
        await update.message.reply_text(
            "✨ С возвращением в StyleVerse!\n\nВыбери что хочешь сделать:",
            reply_markup=main_menu_keyboard(True, has_lora)
        )
        return

    await update.message.reply_text(
        "👋 Привет! Я StyleVerse — AI-бот который вставляет тебя в любую локацию.\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "🤖 ЧТО Я УМЕЮ:\n"
        "━━━━━━━━━━━━━━━━\n\n"
        "🌍 ВСТАВКА В СЦЕНУ\n"
        "Выбираешь локацию из готового списка или описываешь своими словами — "
        "я создаю реалистичное фото где ты находишься в этом месте.\n\n"
        "Пляж в Майами, ночное Токио, Дубай на закате, красная дорожка, "
        "снежные горы — любое место за 1-2 минуты.\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "📌 КАК НАЧАТЬ:\n"
        "━━━━━━━━━━━━━━━━\n\n"
        "1️⃣ Загрузи своё фото (лучше портрет, хорошее освещение)\n"
        "2️⃣ Выбери локацию из списка или напиши своё описание\n"
        "3️⃣ Жди результат ~1-2 минуты\n\n"
        "💡 Чем чётче фото лица — тем лучше результат.\n\n"
        "⬇️ Нажми кнопку ниже чтобы начать:",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📸 Загрузить своё фото", callback_data="update_photo")]
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
        "• Описывай сцену детально: не просто 'пляж', а 'пляж в Майами на закате'\n"
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

    elif query.data == "update_photo":
        context.user_data["state"] = STATE_WAITING_PROFILE
        await query.edit_message_text(
            "📸 Пришли своё фото.\n\n"
            "Лучший результат: портрет с чётким лицом, хорошее освещение."
        )

    elif query.data == "scene":
        if not storage.has_profile_photo(user_id):
            await query.edit_message_text(
                "Сначала загрузи своё фото!", reply_markup=main_menu_keyboard(False)
            )
            return
        await query.edit_message_text(
            "🌍 Выбери локацию или напиши своё описание:",
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

    elif query.data.startswith("sp_"):
        idx = query.data[3:]
        if idx == "custom":
            context.user_data["state"] = STATE_WAITING_SCENE
            await query.edit_message_text(
                "✏️ Напиши описание сцены:\n\n"
                "Например: 'в кафе в Париже утром' или 'на яхте в Средиземном море'"
            )
        else:
            label, scene_prompt = SCENE_PRESETS[int(idx)]
            context.user_data["state"] = STATE_IDLE
            status_msg = await query.edit_message_text(
                f"⏳ {label}...\nШаг 1: размещаю в сцене → Шаг 2: восстанавливаю лицо (~1-2 минуты)"
            )
            await _generate_scene(update, context, scene_prompt, status_msg)


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
        status_msg = await update.message.reply_text(
            "⏳ Генерирую изображение...\n"
            "Шаг 1: размещаю в сцене → Шаг 2: восстанавливаю лицо (~1-2 минуты)"
        )
        context.user_data["state"] = STATE_IDLE
        await _generate_scene(update, context, scene_prompt, status_msg)
    else:
        await update.message.reply_text("Используй /start чтобы начать.")


ADMIN_ID = 835360588


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


async def _generate_scene(update, context, scene_prompt: str, status_msg):
    user_id = update.effective_user.id
    person_path = storage.get_profile_photo_path(user_id)
    chat_id = update.effective_chat.id
    try:
        result_url = await ai_service.insert_into_scene(person_path, scene_prompt)
        await status_msg.delete()
        await _send_result(chat_id, context, person_path, result_url, f"✨ Ты в сцене: {scene_prompt}")
    except Exception as e:
        logger.error(f"Scene failed for user {user_id}: {e}")
        await status_msg.edit_text(
            "❌ Ошибка генерации. Повторите попытку через 1-5 минут.",
            reply_markup=BACK_BTN,
        )
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
