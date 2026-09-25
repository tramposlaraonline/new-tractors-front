from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from .demo_withdraw import balance_at, state
from .models import DemoWithdrawBalance


class BalanceAtTests(SimpleTestCase):
    def test_starts_at_200_and_grows_50_per_hour(self):
        start = timezone.now()
        cases = [(timedelta(0), "200.00"), (timedelta(minutes=30), "225.00"), (timedelta(hours=1), "250.00"),
                 (timedelta(seconds=3), "200.04"), (timedelta(hours=24), "1400.00")]
        for elapsed, expected in cases:
            with self.subTest(elapsed=elapsed):
                self.assertEqual(balance_at(start, start + elapsed), Decimal(expected))

    def test_clock_behind_start_never_goes_below_200(self):
        start = timezone.now()
        self.assertEqual(balance_at(start, start - timedelta(minutes=5)), Decimal("200.00"))


class DemoWithdrawStateTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.ana = User.objects.create_user(username="11911111111", password="x")
        self.bia = User.objects.create_user(username="11922222222", password="x")

    def test_first_access_starts_at_200_and_is_saved_once(self):
        first = state(self.ana)
        self.assertEqual(first, {"balance": Decimal("200.00"), "rate_per_hour": Decimal("50.00")})
        state(self.ana)
        self.assertEqual(DemoWithdrawBalance.objects.filter(user=self.ana).count(), 1)

    def test_each_user_has_its_own_value_from_its_own_start(self):
        state(self.ana)
        state(self.bia)
        # Ana começou 2h antes (auto_now_add: só dá para voltar no tempo com update).
        DemoWithdrawBalance.objects.filter(user=self.ana).update(started_at=timezone.now() - timedelta(hours=2))
        self.assertEqual(state(self.ana)["balance"].quantize(Decimal("1")), Decimal("300"))
        self.assertEqual(state(self.bia)["balance"].quantize(Decimal("1")), Decimal("200"))

    def test_value_survives_restart_because_it_lives_in_the_database(self):
        state(self.ana)
        DemoWithdrawBalance.objects.filter(user=self.ana).update(started_at=timezone.now() - timedelta(hours=1))
        # Nada em memória: uma nova leitura (outro processo/deploy) chega ao mesmo valor.
        self.assertEqual(state(self.ana)["balance"].quantize(Decimal("1")), Decimal("250"))
