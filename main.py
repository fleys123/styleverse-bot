import asyncio
import logging
import signal
import sys

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

sys.stderr.write("=== MAIN.PY MODULE LOADED ===\n")
sys.stderr.flush()

import database
import bot as main_bot
import admin_bot
from telegram import InlineKeyboardMarkup, InlineKeyboardButton

sys.stderr.write("=== ALL IMPORTS DONE ===\n")
sys.stderr.flush()


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
    sys.stderr.write("=== run() STARTED ===\n"); sys.stderr.flush()
    database.init_db()

    app1 = main_bot.build_app()
    sys.stderr.write("=== main bot built ===\n"); sys.stderr.flush()

    try:
        app2 = admin_bot.build_app()
        sys.stderr.write("=== admin bot built OK ===\n"); sys.stderr.flush()
    except Exception as e:
        sys.stderr.write(f"=== admin bot build FAILED: {e!r} ===\n"); sys.stderr.flush()
        logging.error(f"Admin bot build failed: {e}")
        app2 = None

    await app1.initialize()
    sys.stderr.write("=== main bot initialized ===\n"); sys.stderr.flush()

    if app2:
        try:
            await app2.initialize()
            sys.stderr.write("=== admin bot initialized ===\n"); sys.stderr.flush()
        except Exception as e:
            sys.stderr.write(f"=== admin bot initialize FAILED: {e!r} ===\n"); sys.stderr.flush()
            app2 = None

    await app1.start()
    sys.stderr.write("=== main bot started ===\n"); sys.stderr.flush()

    if app2:
        try:
            await app2.start()
            sys.stderr.write("=== admin bot started ===\n"); sys.stderr.flush()
        except Exception as e:
            sys.stderr.write(f"=== admin bot start FAILED: {e!r} ===\n"); sys.stderr.flush()
            app2 = None

    await app1.updater.start_polling()
    sys.stderr.write("=== main bot polling ===\n"); sys.stderr.flush()

    if app2:
        try:
            await app2.updater.start_polling()
            sys.stderr.write("=== admin bot polling ===\n"); sys.stderr.flush()
        except Exception as e:
            sys.stderr.write(f"=== admin bot polling FAILED: {e!r} ===\n"); sys.stderr.flush()

    asyncio.create_task(_check_subscriptions(app1))
    logging.info("Both bots started successfully.")

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
