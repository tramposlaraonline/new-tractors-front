"""Sobe o saldo de DEMONSTRAÇÃO (FRONTEND_DEMO_WITHDRAW) de todas as contas em um valor.

    python manage.py bump_demo_balance --amount 8000 [--todos] [--dry-run]

O saldo de demonstração não fica guardado: é START + RATE_PER_HOUR * horas desde o started_at de cada
conta (preview/demo_withdraw.py). Então somar X reais é recuar o started_at de X / RATE_PER_HOUR horas de
todo mundo — o número continua crescendo R$ 50/h a partir dali, e continua com o selo de demonstração na
tela. Nada é gravado a cada consulta.

`--todos` também cria o registro das contas que nunca abriram a tela (o saldo delas começa em R$ 200 no
primeiro acesso; sem o registro criado aqui, elas não entram no aumento).

Só mexe no saldo fictício do preview local (`preview.sqlite3`). Num backend que paga saque de verdade,
creditar valor que não veio de depósito é fabricar dinheiro — aí o caminho é o livro-caixa do projeto.
"""
from decimal import Decimal, InvalidOperation

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from preview.demo_withdraw import RATE_PER_HOUR, balance_at
from preview.models import DemoWithdrawBalance


class Command(BaseCommand):
    help = "Recua o início do saldo de demonstração de todas as contas, para somar um valor a elas."

    def add_arguments(self, parser):
        parser.add_argument("--amount", type=Decimal, required=True, help="quanto somar a cada conta (ex.: 8000)")
        parser.add_argument("--todos", action="store_true",
                            help="inclui as contas que nunca abriram a tela de saque (cria o registro delas)")
        parser.add_argument("--dry-run", action="store_true", help="só mostra o que seria feito")

    def handle(self, *args, **options):
        amount = options["amount"]
        if amount <= 0:
            raise CommandError("--amount tem que ser maior que zero.")
        # Recuar o início em X / 50 horas. Decimal na multiplicação, para não acumular erro de float.
        seconds = (amount / RATE_PER_HOUR) * Decimal(3600)
        self.shift = timezone.timedelta(microseconds=int(seconds * 1_000_000))
        self.dry_run = options["dry_run"]

        now = timezone.now()
        records = list(DemoWithdrawBalance.objects.select_related("user"))
        if options["todos"]:
            records += self._missing(now)

        if self.dry_run:
            self.stdout.write(self.style.WARNING(
                f"--dry-run: recuando o início em {self.shift} de {len(records)} contas."))
            for record in records[:3]:
                self.stdout.write(f"  {record.user.get_username()}: passaria a "
                                  f"{balance_at(record.started_at - self.shift, now)}")
            return

        with transaction.atomic():
            for record in records:
                DemoWithdrawBalance.objects.filter(pk=record.pk).update(started_at=record.started_at - self.shift)

        self.stdout.write(self.style.SUCCESS(
            f"+R$ {amount:,.2f} em {len(records)} contas de demonstração (cada uma passa a contar de "
            f"{self.shift} atrás).".replace(",", ".")
            + f" Valor agora: {balance_at(now - self.shift, now)}."))

    def _missing(self, now):
        """Registros novos (started_at já recuado) para as contas que nunca abriram a tela."""
        sem_registro = get_user_model().objects.exclude(
            pk__in=DemoWithdrawBalance.objects.values("user_id"))
        novos = [DemoWithdrawBalance(user=user, started_at=now - self.shift) for user in sem_registro]
        if novos and not self.dry_run:
            DemoWithdrawBalance.objects.bulk_create(novos, batch_size=500)
        return novos
