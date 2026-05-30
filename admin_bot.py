import logging
import os

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes

import database


def _main_bot() -> Bot:
    return Bot(token=(os.getenv("TELEGRAM_BOT_TOKEN") or "").strip())

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

        uid, username, full_name, joined, gens, status, sub_until, sub_gens = user
        if status == "vip" and not sub_until:
            status_str = "👑 VIP (безлимит)"
        elif status == "vip" and sub_until:
            status_str = f"🎁 Подписка до {sub_until[:10]}"
        elif status == "banned":
            status_str = "🚫 Заблокирован"
        else:
            status_str = "✅ Активен"
        name = f"@{username}" if username else full_name or str(uid)

        text = (
            f"👤 {name}\n"
            f"🆔 ID: <code>{uid}</code>\n"
            f"📅 Дата: {joined[:10]}\n"
            f"🎨 Генераций: {gens}\n"
            f"📌 Статус: {status_str}"
        )
        if status == "vip" and sub_until:
            text += f"\n📊 Использовано: {sub_gens}/20"

        buttons = []
        buttons.append([InlineKeyboardButton("🎁 Подписка 30д", callback_data=f"adm_sub_{uid}")])
        buttons.append([InlineKeyboardButton("👑 VIP (безлимит)", callback_data=f"adm_vip_{uid}")])
        if status != "banned":
            buttons.append([InlineKeyboardButton("🚫 Заблокировать", callback_data=f"adm_ban_{uid}")])
        if status in ("banned", "vip"):
            buttons.append([InlineKeyboardButton("✅ Сбросить", callback_data=f"adm_reset_{uid}")])
        buttons.append([InlineKeyboardButton("🔙 Список", callback_data="adm_users_0")])

        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="HTML")

    elif data.startswith("adm_sub_"):
        uid = int(data.split("_")[2])
        until = database.activate_subscription(uid, days=30)
        until_fmt = until[:10].replace("-", ".")
        try:
            await _main_bot().send_message(
                chat_id=uid,
                text=(
                    f"🎁 Вам активирована подписка StyleVerse!\n\n"
                    f"✅ 20 генераций на 30 дней\n"
                    f"📅 Действует до: {until_fmt}\n\n"
                    f"/start"
                ),
            )
        except Exception:
            pass
        await query.answer(f"🎁 Подписка выдана до {until_fmt}!", show_alert=True)
        query.data = f"adm_user_{uid}"
        await handle_callback(update, context)

    elif data.startswith("adm_vip_"):
        uid = int(data.split("_")[2])
        database.set_vip(uid)
        try:
            await _main_bot().send_message(
                chat_id=uid,
                text=(
                    "👑 Вам выдан VIP-статус StyleVerse!\n\n"
                    "✅ Безлимитные генерации\n"
                    "🚀 Без ограничений по времени\n\n"
                    "/start"
                ),
            )
        except Exception:
            pass
        await query.answer("👑 VIP выдан (безлимит)!", show_alert=True)
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
    token = (os.getenv("ADMIN_BOT_TOKEN") or "").strip()
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
