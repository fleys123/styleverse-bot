import asyncio
import logging
import os

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

    async with app1, app2:
        await app1.start()
        await app2.start()
        await app1.updater.start_polling()
        await app2.updater.start_polling()

        logging.info("Both bots running. Press Ctrl+C to stop.")
        await asyncio.Event().wait()

        await app1.updater.stop()
        await app2.updater.stop()
        await app1.stop()
        await app2.stop()


if __name__ == "__main__":
    asyncio.run(run())
