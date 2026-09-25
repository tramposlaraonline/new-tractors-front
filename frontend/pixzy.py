"""Cliente mínimo da API Pixzy para o plano VIP."""
import logging
import requests
from django.conf import settings

logger = logging.getLogger(__name__)

VIP_AMOUNT = getattr(settings, "VIP_AMOUNT_CENTS", 4790)


def create_vip_transaction(user, webhook_url: str) -> dict:
    """
    Cria cobrança PIX na Pixzy.
    Retorna: {ok, transaction_id, br_code, amount} ou {ok: False, message}
    """
    token = getattr(settings, "PIXZY_API_TOKEN", "")
    base = getattr(settings, "PIXZY_API_BASE", "https://app.pixzypay.com/api").rstrip("/")

    if not token:
        return {"ok": False, "message": "Pagamento VIP indisponível no momento."}

    name = (user.get_full_name() or "").strip() or user.get_username()
    email = getattr(user, "email", "") or f"{user.get_username()}@newtractors.local"
    # username no projeto é o celular (só dígitos)
    phone = user.get_username()
    # CPF: ajuste se você tiver o campo real no user/profile
    doc = getattr(user, "cpf", None) or getattr(getattr(user, "profile", None), "cpf", None) or "00000000000"

    payload = {
        "amount": VIP_AMOUNT,
        "client_name": name,
        "client_email": email,
        "client_doc": str(doc).replace(".", "").replace("-", ""),
        "client_phone": phone,
        "webhook_url": webhook_url,
        "metadata": {
            "user_id": user.id,
            "product": "vip",
        },
        "items": [
            {
                "name": "Plano VIP New Tractors",
                "price": VIP_AMOUNT,
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
            "amount": int(data.get("amount") or VIP_AMOUNT),
        }
    except requests.RequestException as e:
        logger.exception("Pixzy connection error: %s", e)
        return {"ok": False, "message": "Falha de conexão com o gateway. Tente novamente."}


def get_transaction(transaction_id: str) -> dict | None:
    token = getattr(settings, "PIXZY_API_TOKEN", "")
    base = getattr(settings, "PIXZY_API_BASE", "https://app.pixzypay.com/api").rstrip("/")
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