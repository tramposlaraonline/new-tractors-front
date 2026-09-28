"""Cliente Pixzy: VIP + depósitos."""
import logging
import requests
from django.conf import settings

logger = logging.getLogger(__name__)

VIP_AMOUNT = getattr(settings, "VIP_AMOUNT_CENTS", 4790)


def _token_and_base():
    token = getattr(settings, "PIXZY_API_TOKEN", "") or ""
    base = getattr(settings, "PIXZY_API_BASE", "https://app.pixzypay.com/api").rstrip("/")
    return token, base


def _client_doc(user):
    doc = getattr(user, "cpf", None)
    if not doc:
        profile = getattr(user, "profile", None)
        doc = getattr(profile, "cpf", None) if profile else None
    if not doc:
        try:
            from .models import UserProfile
            p = UserProfile.objects.filter(user=user).first()
            doc = p.cpf if p else None
        except Exception:
            doc = None
    return str(doc or "00000000000").replace(".", "").replace("-", "")


def create_transaction(*, user, amount_cents: int, webhook_url: str, product: str, item_name: str) -> dict:
    """
    Cria cobrança PIX na Pixzy.
    amount_cents: valor em centavos (mín. 500 = R$ 5,00).
    """
    token, base = _token_and_base()
    if not token:
        return {"ok": False, "message": "Gateway de pagamento não configurado."}

    if amount_cents < 500:
        return {"ok": False, "message": "Valor mínimo é R$ 5,00."}

    name = (user.get_full_name() or "").strip() or user.get_username()
    email = getattr(user, "email", "") or f"{user.get_username()}@newtractors.local"
    phone = user.get_username()

    payload = {
        "amount": int(amount_cents),
        "client_name": name,
        "client_email": email,
        "client_doc": _client_doc(user),
        "client_phone": phone,
        "webhook_url": webhook_url,
        "metadata": {
            "user_id": user.id,
            "product": product,
        },
        "items": [
            {
                "name": item_name,
                "price": int(amount_cents),
                "quantity": 1,
            }
        ],
    }

    try:
        r = requests.post(
            f"{base}/transactions",
            json=payload,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            timeout=20,
        )
        body = r.json() if r.content else {}
        if r.status_code >= 400:
            logger.warning("Pixzy error %s: %s", r.status_code, body)
            msg = body.get("error") or body.get("errors") or "Não foi possível gerar o PIX."
            return {"ok": False, "message": str(msg)}

        data = body.get("data") or body
        tx_id = data.get("transaction_id") or data.get("id")
        br_code = data.get("br_code") or data.get("pix_code") or ""
        if not tx_id or not br_code:
            return {"ok": False, "message": "Resposta inválida do gateway."}

        return {
            "ok": True,
            "transaction_id": str(tx_id),
            "br_code": br_code,
            "amount": int(data.get("amount") or amount_cents),
        }
    except requests.RequestException as e:
        logger.exception("Pixzy connection error: %s", e)
        return {"ok": False, "message": "Falha de conexão com o gateway. Tente novamente."}


def create_vip_transaction(user, webhook_url: str) -> dict:
    return create_transaction(
        user=user,
        amount_cents=VIP_AMOUNT,
        webhook_url=webhook_url,
        product="vip",
        item_name="Plano VIP New Tractors",
    )


def create_deposit_transaction(user, amount_cents: int, webhook_url: str) -> dict:
    return create_transaction(
        user=user,
        amount_cents=amount_cents,
        webhook_url=webhook_url,
        product="deposit",
        item_name="Depósito PIX New Tractors",
    )


def get_transaction(transaction_id: str) -> dict | None:
    token, base = _token_and_base()
    if not token:
        return None
    try:
        r = requests.get(
            f"{base}/transactions/{transaction_id}",
            headers={"Authorization": f"Bearer {token}"},
            timeout=15,
        )
        if r.status_code != 200:
            return None
        body = r.json()
        return body.get("data") or body
    except requests.RequestException:
        return None