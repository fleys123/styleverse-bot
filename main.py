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
import webhook_server


async def run():
    database.init_db()

    app1 = main_bot.build_app()
    app2 = admin_bot.build_app()

    webhook_server.set_bot_app(app1)

    await app1.initialize()
    await app2.initialize()

    await app1.start()
    await app2.start()

    await app1.updater.start_polling()
    await app2.updater.start_polling()

    webhook_runner = await webhook_server.start_webhook_server()

    logging.info("Both bots and webhook server started successfully.")

    stop_event = asyncio.Event()
    loop = asyncio.get_event_loop()
    loop.add_signal_handler(signal.SIGINT, stop_event.set)
    loop.add_signal_handler(signal.SIGTERM, stop_event.set)

    await stop_event.wait()

    await webhook_runner.cleanup()
    await app1.updater.stop()
    await app2.updater.stop()
    await app1.stop()
    await app2.stop()
    await app1.shutdown()
    await app2.shutdown()


if __name__ == "__main__":
    asyncio.run(run())
