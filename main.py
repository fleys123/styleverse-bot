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

    # Report startup result to admin via main bot
    try:
        if admin_error:
            msg = f"⚠️ Admin bot не запустился\n\nОшибка: {admin_error}"
        else:
            msg = "✅ Оба бота запущены"
        await app1.bot.send_message(chat_id=ADMIN_ID, text=msg)
    except Exception:
        pass

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
