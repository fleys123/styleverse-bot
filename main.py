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
    print(">>> ENTRY run()", flush=True)
    database.init_db()
    print(">>> DB init done", flush=True)

    app1 = main_bot.build_app()
    print(">>> Main bot built", flush=True)

    try:
        app2 = admin_bot.build_app()
        print(">>> Admin bot built OK", flush=True)
        logging.info("Admin bot app built.")
    except Exception as e:
        print(f">>> Admin bot build FAILED: {e!r}", flush=True)
        logging.error(f"Admin bot build failed: {e}")
        app2 = None

    await app1.initialize()
    print(">>> Main bot initialized", flush=True)

    if app2:
        try:
            await app2.initialize()
            print(">>> Admin bot initialized", flush=True)
        except Exception as e:
            print(f">>> Admin bot initialize FAILED: {e!r}", flush=True)
            app2 = None

    await app1.start()
    print(">>> Main bot started", flush=True)

    if app2:
        try:
            await app2.start()
            print(">>> Admin bot started", flush=True)
        except Exception as e:
            print(f">>> Admin bot start FAILED: {e!r}", flush=True)
            app2 = None

    await app1.updater.start_polling()
    print(">>> Main bot polling", flush=True)

    if app2:
        try:
            await app2.updater.start_polling()
            print(">>> Admin bot polling", flush=True)
        except Exception as e:
            print(f">>> Admin bot polling FAILED: {e!r}", flush=True)

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
