import json
import logging
import os

from aiohttp import web

import database
import payment

logger = logging.getLogger(__name__)

_bot_app = None  # будет установлен из main.py


def set_bot_app(app):
    global _bot_app
    _bot_app = app


async def handle_yukassa(request: web.Request) -> web.Response:
    try:
        payload = await request.json()
    except Exception:
        return web.Response(status=400, text="Bad JSON")

    success, user_id = payment.is_payment_succeeded(payload)
    if not success or not user_id:
        return web.Response(status=200, text="ok")

    try:
        until = database.activate_subscription(user_id, days=payment.SUB_DAYS)
        until_fmt = until[:10].replace("-", ".")
        logger.info(f"Subscription activated for user {user_id} until {until_fmt}")

        if _bot_app:
            try:
                await _bot_app.bot.send_message(
                    chat_id=user_id,
                    text=(
                        f"🎉 Оплата прошла успешно!\n\n"
                        f"✅ 20 генераций активированы\n"
                        f"📅 Подписка действует до: {until_fmt}\n\n"
                        f"/start"
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to notify user {user_id}: {e}")
    except Exception as e:
        logger.error(f"Failed to activate subscription for {user_id}: {e}")
        return web.Response(status=500, text="error")

    return web.Response(status=200, text="ok")


def build_webhook_app() -> web.Application:
    app = web.Application()
    app.router.add_post("/yukassa/webhook", handle_yukassa)
    return app


async def start_webhook_server():
    port = int(os.environ.get("WEBHOOK_PORT", "8080"))
    app = build_webhook_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info(f"Webhook server started on port {port}")
    return runner
