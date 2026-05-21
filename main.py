import logging
import threading

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

import database
import bot as main_bot
import admin_bot


def run_main():
    logging.info("Starting main bot...")
    main_bot.build_app().run_polling()


def run_admin():
    logging.info("Starting admin bot...")
    admin_bot.build_app().run_polling()


if __name__ == "__main__":
    database.init_db()

    t1 = threading.Thread(target=run_main, name="main-bot")
    t2 = threading.Thread(target=run_admin, name="admin-bot")

    t1.start()
    t2.start()

    t1.join()
    t2.join()
