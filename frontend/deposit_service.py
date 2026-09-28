"""Providers reais de depósito/CPF/saldo via Pixzy + banco."""
from decimal import Decimal
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import DepositCharge, UserProfile
from .pixzy import create_deposit_transaction, get_transaction
from .validators import mask_cpf


def _profile(user) -> UserProfile:
    profile, _ = UserProfile.objects.get_or_create(user=user)
    return profile


def wallet_summary(user):
    p = _profile(user)
    invest = p.invest_balance or Decimal("0")
    withdraw = p.withdraw_balance or Decimal("0")
    return {
        "invest_balance": invest,       # só sobe com depósito pago
        "withdraw_balance": withdraw,   # saldo de saque
        "total_balance": withdraw,      # Meu Patrimônio = saldo para saque
    }


def deposit_state(user):
    p = _profile(user)
    cpf = p.cpf or ""
    return {
        "min_amount": Decimal(str(getattr(settings, "DEPOSIT_MIN_AMOUNT", "25"))),
        "max_amount": Decimal(str(getattr(settings, "DEPOSIT_MAX_AMOUNT", "50000"))),
        "presets": [Decimal(str(v)) for v in getattr(settings, "DEPOSIT_PRESETS", [50, 150, 300, 500, 1000, 2000])],
        "cpf_registered": bool(cpf),
        "cpf_masked": mask_cpf(cpf) if len(cpf) == 11 else "",
    }


def register_cpf(user, cpf):
    p = _profile(user)
    p.cpf = cpf  # já vem só dígitos da view
    p.save(update_fields=["cpf", "updated_at"])
    return {"ok": True}


def create_deposit(user, amount, idempotency_key):
    amount = Decimal(amount)
    amount_cents = int(amount * 100)

    # Idempotência
    if idempotency_key:
        existing = DepositCharge.objects.filter(user=user, idempotency_key=idempotency_key).first()
        if existing:
            return {"ok": True, "charge_id": existing.transaction_id}

    p = _profile(user)
    if not p.cpf:
        return {"ok": False, "message": "Cadastre o CPF do titular antes de depositar."}

    webhook = f"{settings.PIXZY_WEBHOOK_BASE.rstrip('/')}/webhooks/pixzy/deposit"
    result = create_deposit_transaction(user, amount_cents, webhook)
    if not result.get("ok"):
        return {"ok": False, "message": result.get("message") or "Erro ao gerar PIX."}

    charge = DepositCharge.objects.create(
        user=user,
        transaction_id=result["transaction_id"],
        amount_cents=result["amount"],
        br_code=result["br_code"],
        status="pending",
        idempotency_key=idempotency_key or "",
        expires_at=timezone.now() + timedelta(minutes=30),
    )
    return {"ok": True, "charge_id": charge.transaction_id}


def deposit_charge(user, charge_id):
    charge = DepositCharge.objects.filter(user=user, transaction_id=charge_id).first()
    if not charge:
        return None
    if charge.status == "pending" and charge.expires_at and timezone.now() > charge.expires_at:
        charge.status = "expired"
        charge.save(update_fields=["status"])
    return {
        "amount": Decimal(charge.amount_cents) / 100,
        "pix_code": charge.br_code,
        "qr_image": "",
        "expires_at": charge.expires_at,
        "status": charge.status,
    }


def deposit_status(user, charge_id, manual_check=False):
    charge = DepositCharge.objects.filter(user=user, transaction_id=charge_id).first()
    if not charge:
        return {"ok": False, "message": "Cobrança não encontrada."}

    if charge.status == "paid":
        return {"ok": True, "status": "paid"}

    if charge.status in ("expired", "failed"):
        return {"ok": True, "status": charge.status}

    # Consulta opcional na API (além do webhook)
    remote = get_transaction(charge_id)
    if remote:
        remote_status = (remote.get("status") or "").lower()
        if remote_status in ("paid", "approved", "completed"):
            mark_deposit_paid(charge)
            return {"ok": True, "status": "paid"}
        if remote_status in ("expired", "failed", "cancelled"):
            charge.status = "expired" if "expir" in remote_status else "failed"
            charge.save(update_fields=["status"])
            return {"ok": True, "status": charge.status}

    return {"ok": True, "status": charge.status}


@transaction.atomic
def mark_deposit_paid(charge: DepositCharge):
    if charge.status == "paid":
        return
    # lock
    charge = DepositCharge.objects.select_for_update().get(pk=charge.pk)
    if charge.status == "paid":
        return
    charge.status = "paid"
    charge.paid_at = timezone.now()
    charge.save(update_fields=["status", "paid_at"])

    amount = Decimal(charge.amount_cents) / 100
    profile = _profile(charge.user)
    profile.invest_balance = (profile.invest_balance or Decimal("0")) + amount
    profile.save(update_fields=["invest_balance", "updated_at"])

    # Sincroniza memória do preview (se existir)
    try:
        from preview import demo_data
        with demo_data._lock:
            s = demo_data._get(charge.user)
            s["invest"] += amount
            demo_data._log(
                s, "deposit", "Depósito PIX Instantâneo",
                "Transferência recebida via Pix", amount,
            )
    except Exception:
        pass