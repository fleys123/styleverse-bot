import logging
import os

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes

import database

logger = logging.getLogger(__name__)

ADMIN_ID = 835360588


def _is_admin(update: Update) -> bool:
    return update.effective_user.id == ADMIN_ID


def _main_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Статистика", callback_data="adm_stats")],
        [InlineKeyboardButton("👥 Пользователи", callback_data="adm_users_0")],
    ])


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update):
        return
    await update.message.reply_text("👑 StyleVerse Admin", reply_markup=_main_kb())


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update):
        return
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "adm_menu":
        await query.edit_message_text("👑 StyleVerse Admin", reply_markup=_main_kb())

    elif data == "adm_stats":
        s = database.get_stats()
        text = (
            f"📊 Статистика StyleVerse\n\n"
            f"👥 Всего пользователей: {s['total']}\n"
            f"🆕 За сегодня: {s['today']}\n"
            f"🎨 Генераций всего: {s['generations']}\n"
            f"🎁 VIP: {s['vip']}\n"
            f"🚫 Заблокировано: {s['banned']}"
        )
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 Обновить", callback_data="adm_stats")],
            [InlineKeyboardButton("🔙 Меню", callback_data="adm_menu")],
        ]))

    elif data.startswith("adm_users_"):
        offset = int(data.split("_")[2])
        users = database.get_users(limit=10, offset=offset)
        if not users:
            await query.edit_message_text(
                "Нет пользователей.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Меню", callback_data="adm_menu")]]),
            )
            return

        buttons = []
        for uid, username, full_name, joined, gens, status in users:
            icon = "🎁" if status == "vip" else "🚫" if status == "banned" else "👤"
            name = f"@{username}" if username else full_name or str(uid)
            buttons.append([InlineKeyboardButton(f"{icon} {name} · {gens} gen", callback_data=f"adm_user_{uid}")])

        nav = []
        if offset > 0:
            nav.append(InlineKeyboardButton("◀️", callback_data=f"adm_users_{offset - 10}"))
        if len(users) == 10:
            nav.append(InlineKeyboardButton("▶️", callback_data=f"adm_users_{offset + 10}"))
        if nav:
            buttons.append(nav)
        buttons.append([InlineKeyboardButton("🔙 Меню", callback_data="adm_menu")])

        await query.edit_message_text(
            f"👥 Пользователи (с {offset + 1}):",
            reply_markup=InlineKeyboardMarkup(buttons),
        )

    elif data.startswith("adm_user_"):
        uid = int(data.split("_")[2])
        user = database.get_user(uid)
        if not user:
            await query.edit_message_text("Пользователь не найден.")
            return

        uid, username, full_name, joined, gens, status = user
        status_str = "🎁 VIP" if status == "vip" else "🚫 Заблокирован" if status == "banned" else "✅ Активен"
        name = f"@{username}" if username else full_name or str(uid)

        text = (
            f"👤 {name}\n"
            f"🆔 ID: `{uid}`\n"
            f"📅 Дата: {joined[:10]}\n"
            f"🎨 Генераций: {gens}\n"
            f"📌 Статус: {status_str}"
        )

        buttons = []
        if status != "vip":
            buttons.append([InlineKeyboardButton("🎁 Выдать VIP", callback_data=f"adm_setvip_{uid}")])
        if status != "banned":
            buttons.append([InlineKeyboardButton("🚫 Заблокировать", callback_data=f"adm_ban_{uid}")])
        if status in ("banned", "vip"):
            buttons.append([InlineKeyboardButton("✅ Сбросить", callback_data=f"adm_reset_{uid}")])
        buttons.append([InlineKeyboardButton("🔙 Список", callback_data="adm_users_0")])

        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="Markdown")

    elif data.startswith("adm_setvip_"):
        uid = int(data.split("_")[2])
        database.set_status(uid, "vip")
        await query.answer("🎁 VIP выдан!", show_alert=True)
        query.data = f"adm_user_{uid}"
        await handle_callback(update, context)

    elif data.startswith("adm_ban_"):
        uid = int(data.split("_")[2])
        database.set_status(uid, "banned")
        await query.answer("🚫 Заблокирован!", show_alert=True)
        query.data = f"adm_user_{uid}"
        await handle_callback(update, context)

    elif data.startswith("adm_reset_"):
        uid = int(data.split("_")[2])
        database.set_status(uid, "active")
        await query.answer("✅ Статус сброшен!", show_alert=True)
        query.data = f"adm_user_{uid}"
        await handle_callback(update, context)


def build_app() -> Application:
    token = os.getenv("ADMIN_BOT_TOKEN")
    if not token:
        raise ValueError("Укажи ADMIN_BOT_TOKEN в .env")
    app = (
        Application.builder()
        .token(token)
        .connect_timeout(30)
        .read_timeout(30)
        .write_timeout(30)
        .build()
    )
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CallbackQueryHandler(handle_callback))
    return app
