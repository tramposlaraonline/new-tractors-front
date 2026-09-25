"""Enche a fila de saque de demonstração com pedidos reais de usuários de demonstração.

    python manage.py seed_queue --count 3000

Cada pedido vira uma linha em preview.DemoQueuedWithdrawal, com dono e horário de chegada, e é
contado pela fila do preview (preview/demo_data.py). Assim a posição que o cartão mostra é a
contagem real dos pedidos que chegaram antes: o usuário que pedir o saque agora entra como
--count + 1 e só anda quando a fila liquidar os da frente.

A fila só não anda sozinha porque o preview tem teto de liquidação por dia
(preview/demo_data.py: DAILY_PAYOUT_LIMIT): o que passa do teto espera o dia seguinte. Os usuários
criados não têm senha utilizável (não dá para entrar com eles) e o comando reconstrói a fila
semeada do zero a cada execução.
"""
import random
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from preview.demo_data import REVIEW_SECONDS
from preview.models import DemoQueuedWithdrawal

USERNAME_PREFIX = "demo-fila-"
CHUNK = 500  # usernames por consulta (o SQLite tem limite de parâmetros por query)


def _chunks(items, size):
    for start in range(0, len(items), size):
        yield items[start:start + size]


class Command(BaseCommand):
    help = "Cria N saques pendentes de usuários de demonstração, para a fila de saque do preview."

    def add_arguments(self, parser):
        parser.add_argument("--count", type=int, default=3000, help="quantos saques pendentes criar (padrão: 3000)")
        parser.add_argument("--window", type=float, default=float(REVIEW_SECONDS),
                            help=f"segundos distribuídos entre a chegada do primeiro e do último pedido "
                                 f"(padrão: {REVIEW_SECONDS})")
        parser.add_argument("--min-amount", type=Decimal, default=Decimal("5.00"))
        parser.add_argument("--max-amount", type=Decimal, default=Decimal("500.00"))
        parser.add_argument("--seed", type=int, help="deixa o sorteio reproduzível (mesmos valores)")

    def handle(self, *args, **options):
        count = options["count"]
        window = options["window"]
        min_amount, max_amount = options["min_amount"], options["max_amount"]
        if count < 1:
            raise CommandError("--count tem que ser no mínimo 1.")
        if window < 0:
            raise CommandError("--window não pode ser negativo.")
        if min_amount <= 0 or max_amount < min_amount:
            raise CommandError("--min-amount tem que ser positivo e menor ou igual a --max-amount.")
        if window > REVIEW_SECONDS:
            self.stdout.write(self.style.WARNING(
                f"Atenção: com --window {window:g}, os pedidos mais antigos da fila semeada já nascem vencidos "
                f"(o preview liquida um a cada {REVIEW_SECONDS}s) e saem todos de uma vez na primeira tela aberta, "
                f"até bater o limite diário. Use --window {REVIEW_SECONDS} para a fila estar cheia na hora da demo."))

        rng = random.Random(options["seed"])  # sem --seed, cada execução sorteia valores diferentes
        usernames = [f"{USERNAME_PREFIX}{i:05d}" for i in range(count)]
        first_arrival = timezone.now() - timedelta(seconds=window)
        spacing = window / (count - 1) if count > 1 else 0.0

        with transaction.atomic():
            User = get_user_model()
            DemoQueuedWithdrawal.objects.filter(user__username__startswith=USERNAME_PREFIX).delete()
            User.objects.filter(username__startswith=USERNAME_PREFIX).delete()
            pks = self._demo_users(User, usernames)
            DemoQueuedWithdrawal.objects.bulk_create(
                [DemoQueuedWithdrawal(user_id=pks[username], status="pending",
                                      amount=(min_amount + (max_amount - min_amount) * Decimal(str(rng.random())))
                                      .quantize(Decimal("0.01")),
                                      created_at=first_arrival + timedelta(seconds=spacing * index))
                 for index, username in enumerate(usernames)], batch_size=CHUNK)

        self.stdout.write(self.style.SUCCESS(
            f"Fila de demonstração montada: {count} saques pendentes, de {count} usuários sem senha. "
            f"O próximo saque entra em {count + 1}º lugar."))

    def _demo_users(self, User, usernames):
        """Garante um usuário sem senha utilizável para cada username e devolve {username: pk}."""
        existing = set()
        for chunk in _chunks(usernames, CHUNK):
            existing.update(User.objects.filter(username__in=chunk).values_list("username", flat=True))
        missing = [User(username=username) for username in usernames if username not in existing]
        for user in missing:
            user.set_unusable_password()
        if missing:
            User.objects.bulk_create(missing, batch_size=CHUNK)
        pks = {}
        for chunk in _chunks(usernames, CHUNK):
            pks.update(User.objects.filter(username__in=chunk).values_list("username", "pk"))
        return pks
