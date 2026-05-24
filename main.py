import asyncio
import logging
import signal

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
    app2 = None
    try:
        app2 = admin_bot.build_app()
    except Exception as e:
        admin_error = f"build_app: {e!r}"

    await app1.initialize()

    if app2:
        try:
            await app2.initialize()
        except Exception as e:
            admin_error = f"initialize: {e!r}"
            app2 = None

    await app1.start()

    if app2:
        try:
            await app2.start()
        except Exception as e:
            admin_error = f"start: {e!r}"
            app2 = None

    await app1.updater.start_polling()

    if app2:
        try:
            await app2.updater.start_polling()
        except Exception as e:
            admin_error = f"start_polling: {e!r}"

    # Report status via main bot (admin has conversation with main bot now)
    try:
        if admin_error:
            await app1.bot.send_message(
                chat_id=ADMIN_ID,
                text=f"⚠️ Admin bot не запустился\n\n<code>{admin_error}</code>",
                parse_mode="HTML",
            )
        else:
            await app1.bot.send_message(chat_id=ADMIN_ID, text="✅ Оба бота запущены")
    except Exception as e:
        logging.error(f"Failed to notify admin: {e}")

    asyncio.create_task(_check_subscriptions(app1))

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
