import ipaddress
import logging
import os

from aiohttp import web

import database
import payment

logger = logging.getLogger(__name__)

# Официальные IP-адреса ЮКассы для webhook-уведомлений
YUKASSA_IPS = [
    ipaddress.ip_network("185.71.76.0/27"),
    ipaddress.ip_network("185.71.77.0/27"),
    ipaddress.ip_network("77.75.153.0/25"),
    ipaddress.ip_network("77.75.156.11/32"),
    ipaddress.ip_network("77.75.156.35/32"),
    ipaddress.ip_network("77.75.154.128/25"),
    ipaddress.ip_network("2a02:5180::/32"),
]

_bot_app = None


def set_bot_app(app):
    global _bot_app
    _bot_app = app


def _is_yukassa_ip(ip_str: str) -> bool:
    try:
        ip = ipaddress.ip_address(ip_str)
        return any(ip in network for network in YUKASSA_IPS)
    except ValueError:
        return False


async def handle_yukassa(request: web.Request) -> web.Response:
    # Проверяем IP — принимаем только от ЮКассы
    ip = request.headers.get("X-Forwarded-For", request.remote).split(",")[0].strip()
    if not _is_yukassa_ip(ip):
        logger.warning(f"Webhook rejected from unknown IP: {ip}")
        return web.Response(status=403, text="Forbidden")

    try:
        payload = await request.json()
    except Exception:
        return web.Response(status=400, text="Bad JSON")

    # Проверяем сумму платежа
    try:
        amount = float(payload.get("object", {}).get("amount", {}).get("value", 0))
        if amount < float(payment.SUB_AMOUNT):
            logger.warning(f"Webhook rejected: wrong amount {amount}")
            return web.Response(status=200, text="ok")
    except Exception:
        pass

    success, user_id = payment.is_payment_succeeded(payload)
    if not success or not user_id:
        return web.Response(status=200, text="ok")

    try:
        until = database.activate_subscription(user_id, days=payment.SUB_DAYS)
        until_fmt = until[:10].replace("-", ".")
        logger.info(f"Subscription activated for user {user_id} until {until_fmt}")

        if _bot_app:
            try:
                from telegram import InlineKeyboardButton, InlineKeyboardMarkup
                await _bot_app.bot.send_message(
                    chat_id=user_id,
                    text=(
                        f"🎉 Оплата прошла успешно!\n\n"
                        f"✅ 20 генераций активированы\n"
                        f"📅 Подписка действует до: {until_fmt}\n\n"
                        f"/start"
                    ),
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🧾 Нужен чек об оплате", callback_data=f"receipt_{user_id}")]
                    ]),
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
