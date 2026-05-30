import os
import uuid
import logging

from yookassa import Configuration, Payment

logger = logging.getLogger(__name__)

SUB_AMOUNT = "799.00"
SUB_CURRENCY = "RUB"
SUB_DAYS = 30


def _configure():
    Configuration.account_id = os.environ["YUKASSA_SHOP_ID"]
    Configuration.secret_key = os.environ["YUKASSA_SECRET_KEY"]


def create_payment(user_id: int, return_url: str) -> tuple[str, str]:
    """
    Create a YuKassa payment for subscription.
    Returns (payment_id, confirmation_url).
    """
    _configure()
    payment = Payment.create({
        "amount": {"value": SUB_AMOUNT, "currency": SUB_CURRENCY},
        "confirmation": {"type": "redirect", "return_url": return_url},
        "capture": True,
        "description": f"Подписка StyleVerse 30 дней (user_id={user_id})",
        "metadata": {"user_id": str(user_id)},
    }, uuid.uuid4())
    return payment.id, payment.confirmation.confirmation_url


def is_payment_succeeded(payload: dict) -> tuple[bool, int | None]:
    """
    Parse YuKassa webhook payload.
    Returns (success, user_id) if payment succeeded, else (False, None).
    """
    try:
        if payload.get("event") != "payment.succeeded":
            return False, None
        obj = payload["object"]
        if obj.get("status") != "succeeded":
            return False, None
        user_id = int(obj["metadata"]["user_id"])
        return True, user_id
    except Exception as e:
        logger.error(f"Failed to parse YuKassa payload: {e}")
        return False, None
