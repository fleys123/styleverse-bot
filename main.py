import asyncio
import logging
import os
import signal

import httpx
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

import database
import bot as main_bot
import admin_bot
from telegram import InlineKeyboardMarkup, InlineKeyboardButton

ADMIN_ID = 835360588
_ADMIN_TOKEN = "".join((os.getenv("ADMIN_BOT_TOKEN") or "").split())


async def _notify_admin(text: str):
    """Send message to admin via admin bot token (direct API, no Application state needed)."""
    if not _ADMIN_TOKEN:
        return
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(
                f"https://api.telegram.org/bot{_ADMIN_TOKEN}/sendMessage",
                json={"chat_id": ADMIN_ID, "text": text},
            )
    except Exception:
        pass


async def _check_subscriptions(app):
    """Hourly job: notify expiring subs, revoke expired ones."""
    while True:
        await asyncio.sleep(3600)
        try:
            expiring = database.get_expiring_subscriptions()
            for user_id, until in expiring:
                try:
                    await app.bot.send_message(
                        chat_id=user_id,
                        text=(
                            f"⏳ Напоминаем: ваша подписка StyleVerse истекает {until[:10]}.\n\n"
                            "Чтобы продолжить пользоваться ботом — продлите подписку 👇"
                        ),
                        reply_markup=InlineKeyboardMarkup([[
                            InlineKeyboardButton("💳 Продлить подписку", url="https://t.me/Fleys2")
                        ]]),
                    )
                except Exception:
                    pass
        except Exception as e:
            logging.error(f"Subscription check error: {e}")


async def run():
    database.init_db()

    app1 = main_bot.build_app()

    admin_error = None
    try:
        app2 = admin_bot.build_app()
    except Exception as e:
        logging.error(f"Admin bot build failed: {e}")
        admin_error = f"build: {e}"
        app2 = None

    await app1.initialize()

    if app2:
        try:
            await app2.initialize()
        except Exception as e:
            logging.error(f"Admin bot initialize failed: {e}")
            admin_error = f"initialize: {e}"
            app2 = None

    await app1.start()

    if app2:
        try:
            await app2.start()
        except Exception as e:
            logging.error(f"Admin bot start failed: {e}")
            admin_error = f"start: {e}"
            app2 = None

    await app1.updater.start_polling()

    if app2:
        try:
            await app2.updater.start_polling()
        except Exception as e:
            logging.error(f"Admin bot polling failed: {e}")
            admin_error = f"polling: {e}"

    if admin_error:
        await _notify_admin(f"⚠️ Admin bot не запустился\n\nОшибка: {admin_error}")
    else:
        await _notify_admin("✅ Оба бота запущены")

    asyncio.create_task(_check_subscriptions(app1))
    logging.info("Startup complete.")

    stop_event = asyncio.Event()
    loop = asyncio.get_event_loop()
    loop.add_signal_handler(signal.SIGINT, stop_event.set)
    loop.add_signal_handler(signal.SIGTERM, stop_event.set)

    await stop_event.wait()

    await app1.updater.stop()
    if app2:
        await app2.updater.stop()
    await app1.stop()
    if app2:
        await app2.stop()
    await app1.shutdown()
    if app2:
        await app2.shutdown()


if __name__ == "__main__":
    asyncio.run(run())
