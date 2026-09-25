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


class DemoWithdrawQueueTests(TestCase):
    """A fila do preview é calculada dos saques de todos os usuários e paga um por vez, em ordem."""

    def setUp(self):
        from unittest import mock

        from . import demo_data
        self.demo = demo_data
        demo_data._state.clear()
        demo_data._payout["last_at"] = None
        self.t0 = timezone.now()
        self.clock = mock.patch("preview.demo_data.timezone.now", return_value=self.t0)
        self.now = self.clock.start()
        self.addCleanup(self.clock.stop)
        self.addCleanup(demo_data._state.clear)
        User = get_user_model()
        self.users = [User.objects.create_user(username=f"1191111111{i}", password="x") for i in range(3)]

    def request_withdraw(self, user, key, at_seconds):
        self.now.return_value = self.t0 + timedelta(seconds=at_seconds)
        return self.demo.withdraw(user, Decimal("1.00"), key)

    def position_at(self, user, at_seconds):
        self.now.return_value = self.t0 + timedelta(seconds=at_seconds)
        queue = self.demo.withdraw_queue(user)
        return queue and (queue["position"], queue["entry_position"])

    def test_withdrawQueue_orderOfArrival_givesPositions(self):
        for i, user in enumerate(self.users):
            self.request_withdraw(user, f"key-{i}", at_seconds=i)

        self.assertEqual([self.position_at(u, 5) for u in self.users], [(1, 1), (2, 2), (3, 3)])

    def test_withdrawQueue_paysOneEvery30sInOrder(self):
        for i, user in enumerate(self.users):
            self.request_withdraw(user, f"key-{i}", at_seconds=i)

        self.assertEqual([self.position_at(u, 31) for u in self.users], [None, (1, 2), (2, 3)])
        self.assertEqual([self.position_at(u, 61) for u in self.users], [None, None, (1, 3)])
        self.assertEqual([self.position_at(u, 91) for u in self.users], [None, None, None])

    def test_withdrawQueue_withoutWithdrawal_isNone(self):
        self.assertIsNone(self.position_at(self.users[0], 0))
