import asyncio
import logging
import signal
import traceback

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
    print("=== STARTUP BEGIN ===", flush=True)
    database.init_db()
    print("DB OK", flush=True)

    app1 = main_bot.build_app()
    print("Main bot built", flush=True)

    try:
        app2 = admin_bot.build_app()
        print("Admin bot built", flush=True)
    except Exception as e:
        print(f"ADMIN BOT BUILD FAILED: {type(e).__name__}: {e}", flush=True)
        traceback.print_exc()
        raise

    await app1.initialize()
    print("Main bot initialized", flush=True)

    try:
        await app2.initialize()
        print("Admin bot initialized", flush=True)
        me2 = await app2.bot.get_me()
        print(f"Admin bot get_me OK: @{me2.username}", flush=True)
    except Exception as e:
        print(f"ADMIN BOT INIT FAILED: {type(e).__name__}: {e}", flush=True)
        traceback.print_exc()
        raise

    await app1.start()
    print("Main bot started", flush=True)
    await app2.start()
    print("Admin bot started", flush=True)

    await app1.updater.start_polling()
    await app2.updater.start_polling()

    print("=== BOTH BOTS POLLING ===", flush=True)

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
