"""Saldo para saque de DEMONSTRAÇÃO (FRONTEND_DEMO_WITHDRAW=1). Valores fictícios, sempre exibidos com o selo
"Seu saldo está sendo calculado".

Cada usuário começa em R$ 200 no primeiro acesso e sobe R$ 50 por hora a partir dali. Como cada um tem o
próprio início, o valor é diferente para cada usuário e continua do mesmo ponto depois de um deploy.
"""
from decimal import ROUND_DOWN, Decimal

from django.utils import timezone

from .models import DemoWithdrawBalance

START = Decimal("200.00")
RATE_PER_HOUR = Decimal("50.00")


def balance_at(started_at, now):
    hours = Decimal(max(0.0, (now - started_at).total_seconds())) / Decimal(3600)
    return (START + RATE_PER_HOUR * hours).quantize(Decimal("0.01"), rounding=ROUND_DOWN)


def state(user):
    """Provider do FRONTEND_DEMO_WITHDRAW_PROVIDER: saldo atual e ritmo (reais por hora) para o contador na tela."""
    # get_or_create já trata dois primeiros acessos simultâneos (OneToOne: o segundo cai no get).
    record, _ = DemoWithdrawBalance.objects.get_or_create(user=user)
    return {"balance": balance_at(record.started_at, timezone.now()), "rate_per_hour": RATE_PER_HOUR}
