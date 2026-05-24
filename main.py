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


async def run():
    database.init_db()

    app1 = main_bot.build_app()
    app2 = admin_bot.build_app()

    await app1.initialize()
    await app2.initialize()

    me1 = await app1.bot.get_me()
    logging.info(f"Main bot OK: @{me1.username}")

    me2 = await app2.bot.get_me()
    logging.info(f"Admin bot OK: @{me2.username}")

    await app1.start()
    await app2.start()

    await app1.updater.start_polling()
    await app2.updater.start_polling()

    logging.info("Both bots started successfully.")

    stop_event = asyncio.Event()
    loop = asyncio.get_event_loop()
    loop.add_signal_handler(signal.SIGINT, stop_event.set)
    loop.add_signal_handler(signal.SIGTERM, stop_event.set)

    await stop_event.wait()

    await app1.updater.stop()
    await app2.updater.stop()
    await app1.stop()
    await app2.stop()
    await app1.shutdown()
    await app2.shutdown()


if __name__ == "__main__":
    asyncio.run(run())
