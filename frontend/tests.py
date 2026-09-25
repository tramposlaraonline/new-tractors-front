import re
from unittest import mock

from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from .forms import GENERIC_LOGIN_ERROR, PHONE_TAKEN_ERROR

JSON = {"HTTP_ACCEPT": "application/json"}


class LoginPageTests(TestCase):
    def test_renders_original_structure(self):
        res = self.client.get(reverse("frontend:login"))
        self.assertEqual(res.status_code, 200)
        for marker in ('id="loginForm"', 'name="mobile"', 'name="password"',
                       'id="authSuccessModal"', 'csrfmiddlewaretoken', 'Entrar na Plataforma'):
            self.assertContains(res, marker)

    def test_authenticated_user_is_redirected_away_from_login(self):
        user = get_user_model().objects.create_user(username="11987654321", password="s3nha-forte")
        self.client.force_login(user)
        res = self.client.get(reverse("frontend:login"))
        self.assertRedirects(res, "/", fetch_redirect_response=False)


@override_settings(FRONTEND_AUTH_LOCKED=False)
class LoginSubmitTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="11987654321", password="s3nha-forte")
        self.url = reverse("frontend:login")

    def test_json_success_returns_redirect_and_logs_in(self):
        res = self.client.post(self.url, {"mobile": "(11) 98765-4321", "password": "s3nha-forte"}, **JSON)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json(), {"ok": True, "redirect": "/"})
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.user.pk)

    def test_accepts_number_pasted_with_country_code(self):
        res = self.client.post(self.url, {"mobile": "+55 11 98765-4321", "password": "s3nha-forte"}, **JSON)
        self.assertTrue(res.json()["ok"])

    def test_wrong_password_and_unknown_phone_get_same_generic_message(self):
        wrong_pass = self.client.post(self.url, {"mobile": "11987654321", "password": "errada"}, **JSON)
        unknown = self.client.post(self.url, {"mobile": "21912345678", "password": "s3nha-forte"}, **JSON)
        for res in (wrong_pass, unknown):
            self.assertEqual(res.status_code, 400)
            self.assertEqual(res.json()["message"], GENERIC_LOGIN_ERROR)
            self.assertEqual(res.json()["errors"], {})
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_inactive_user_gets_generic_message(self):
        self.user.is_active = False
        self.user.save()
        res = self.client.post(self.url, {"mobile": "11987654321", "password": "s3nha-forte"}, **JSON)
        self.assertEqual(res.json()["message"], GENERIC_LOGIN_ERROR)

    def test_field_errors_for_empty_and_invalid_input(self):
        empty = self.client.post(self.url, {"mobile": "", "password": ""}, **JSON).json()
        self.assertEqual(set(empty["errors"]), {"mobile", "password"})
        short = self.client.post(self.url, {"mobile": "1198", "password": "x"}, **JSON).json()
        self.assertEqual(short["errors"]["mobile"], ["Telefone deve ter entre 8 e 11 dígitos."])

    def test_external_next_is_ignored(self):
        res = self.client.post(
            self.url,
            {"mobile": "11987654321", "password": "s3nha-forte", "next": "https://evil.example/phish"},
            **JSON,
        )
        self.assertEqual(res.json()["redirect"], "/")

    def test_internal_next_is_honored(self):
        res = self.client.post(
            self.url, {"mobile": "11987654321", "password": "s3nha-forte", "next": "/equipamentos"}, **JSON
        )
        self.assertEqual(res.json()["redirect"], "/equipamentos")

    def test_without_js_success_redirects(self):
        res = self.client.post(self.url, {"mobile": "11987654321", "password": "s3nha-forte"})
        self.assertRedirects(res, "/", fetch_redirect_response=False)

    def test_without_js_error_renders_page_with_message(self):
        res = self.client.post(self.url, {"mobile": "11987654321", "password": "errada"})
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, GENERIC_LOGIN_ERROR)
        # O telefone digitado é mantido; a senha nunca volta para o HTML.
        self.assertContains(res, 'value="11987654321"')
        self.assertNotContains(res, "errada")

    def test_csrf_is_enforced(self):
        client = Client(enforce_csrf_checks=True)
        res = client.post(self.url, {"mobile": "11987654321", "password": "s3nha-forte"}, **JSON)
        self.assertEqual(res.status_code, 403)


VALID_REGISTRATION = {
    "full_name": "  Maria   da Silva  ",
    "phone": "(11) 98765-4321",
    "password": "s3nha-forte",
    "password_confirmation": "s3nha-forte",
    "invitation_code": " new 2026 ",
}


class RegisterPageTests(TestCase):
    def test_renders_form_and_shared_success_modal(self):
        res = self.client.get(reverse("frontend:register"))
        self.assertEqual(res.status_code, 200)
        for marker in ('id="registerForm"', 'name="full_name"', 'name="phone"', 'name="password"',
                       'name="password_confirmation"', 'name="invitation_code"', 'Concluir Cadastro',
                       'id="authSuccessModal"', 'Acesso Autorizado!', 'csrfmiddlewaretoken'):
            self.assertContains(res, marker)
        # Aba "Criar Conta" ativa no seletor.
        self.assertContains(res, 'aria-current="page"')

    def test_login_page_still_has_success_modal(self):
        self.assertContains(self.client.get(reverse("frontend:login")), "Acesso Autorizado!")

    def test_authenticated_user_is_redirected_away(self):
        user = get_user_model().objects.create_user(username="11987654321", password="s3nha-forte")
        self.client.force_login(user)
        res = self.client.get(reverse("frontend:register"))
        self.assertRedirects(res, "/", fetch_redirect_response=False)


@override_settings(FRONTEND_AUTH_LOCKED=False)
class RegisterSubmitTests(TestCase):
    url = reverse("frontend:register")

    def post(self, **overrides):
        return self.client.post(self.url, {**VALID_REGISTRATION, **overrides}, **JSON)

    def test_success_creates_user_logs_in_and_returns_redirect(self):
        res = self.post()
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json(), {"ok": True, "redirect": "/"})
        user = get_user_model().objects.get(username="11987654321")
        self.assertEqual((user.first_name, user.last_name), ("Maria", "da Silva"))
        self.assertTrue(user.check_password("s3nha-forte"))
        # Já entra logado (não volta para o /login como no original).
        self.assertEqual(int(self.client.session["_auth_user_id"]), user.pk)

    def test_new_user_can_log_in_afterwards(self):
        self.post()
        self.client.logout()
        res = self.client.post(reverse("frontend:login"),
                               {"mobile": "11987654321", "password": "s3nha-forte"}, **JSON)
        self.assertTrue(res.json()["ok"])

    def test_invitation_code_is_normalized_and_handed_to_hook(self):
        with mock.patch("frontend.forms.apply_invitation_code") as hook:
            self.post()
        user, code = hook.call_args.args
        self.assertEqual(code, "NEW2026")
        self.assertEqual(user.username, "11987654321")

    def test_invitation_code_is_optional(self):
        self.assertTrue(self.post(invitation_code="").json()["ok"])

    def test_phone_pasted_with_country_code_is_accepted(self):
        self.assertTrue(self.post(phone="+55 11 98765-4321").json()["ok"])
        self.assertTrue(get_user_model().objects.filter(username="11987654321").exists())

    def test_field_errors_match_original_messages(self):
        data = self.client.post(self.url, {}, **JSON).json()
        self.assertEqual(data["errors"], {
            "full_name": ["Informe seu nome e sobrenome."],
            "phone": ["Telefone deve ter 11 dígitos com DDD."],
            "password": ["A senha deve ter no mínimo 6 caracteres."],
            "password_confirmation": ["Confirme sua senha."],
        })
        self.assertFalse(get_user_model().objects.exists())

    def test_short_name_landline_and_short_password_are_rejected(self):
        errors = self.post(full_name="  Al ", phone="(11) 3456-7890", password="12345",
                           password_confirmation="12345").json()["errors"]
        self.assertEqual(errors["full_name"], ["Informe seu nome e sobrenome."])
        self.assertEqual(errors["phone"], ["Telefone deve ter 11 dígitos com DDD."])
        self.assertEqual(errors["password"], ["A senha deve ter no mínimo 6 caracteres."])

    def test_password_mismatch(self):
        res = self.post(password_confirmation="outra-senha")
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["errors"], {"password_confirmation": ["As senhas não coincidem."]})
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_duplicate_phone_is_reported_on_phone_field(self):
        get_user_model().objects.create_user(username="11987654321", password="outra")
        res = self.post()
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["errors"], {"phone": [PHONE_TAKEN_ERROR]})
        self.assertEqual(get_user_model().objects.count(), 1)

    def test_concurrent_duplicate_is_caught_instead_of_500(self):
        # Outro request criou o mesmo telefone entre a validação e o INSERT.
        with mock.patch("django.contrib.auth.models.UserManager.create_user", side_effect=IntegrityError):
            res = self.post()
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["errors"], {"phone": [PHONE_TAKEN_ERROR]})
        self.assertNotIn("_auth_user_id", self.client.session)

    @override_settings(AUTH_PASSWORD_VALIDATORS=[
        {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
    ])
    def test_project_password_validators_are_applied(self):
        res = self.post(password="12345678", password_confirmation="12345678")
        self.assertEqual(res.status_code, 400)
        self.assertIn("password", res.json()["errors"])

    def test_external_next_is_ignored_and_internal_honored(self):
        evil = self.post(next="https://evil.example/phish").json()
        self.assertEqual(evil["redirect"], "/")
        self.client.logout()
        internal = self.post(phone="11912345678", next="/equipamentos").json()
        self.assertEqual(internal["redirect"], "/equipamentos")

    def test_without_js_success_redirects(self):
        res = self.client.post(self.url, VALID_REGISTRATION)
        self.assertRedirects(res, "/", fetch_redirect_response=False)
        self.assertIn("_auth_user_id", self.client.session)

    def test_without_js_error_keeps_input_but_never_echoes_password(self):
        res = self.client.post(self.url, {**VALID_REGISTRATION, "password_confirmation": "nao-bate"})
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "As senhas não coincidem.")
        # Devolve o que foi digitado (bruto), para o usuário não perder o que preencheu.
        self.assertContains(res, 'value="  Maria   da Silva  "')
        self.assertNotContains(res, "s3nha-forte")
        self.assertNotContains(res, "nao-bate")

    def test_csrf_is_enforced(self):
        client = Client(enforce_csrf_checks=True)
        res = client.post(self.url, VALID_REGISTRATION, **JSON)
        self.assertEqual(res.status_code, 403)
        self.assertFalse(get_user_model().objects.exists())

SPA = {"HTTP_X_SPA_REQUEST": "1", "HTTP_ACCEPT": "application/json"}
APP_ROUTES = [("frontend:home", "home", "Início"), ("frontend:team", "team", "Minha Equipe"),
              ("frontend:deposit", "deposit", "Depositar Saldo Pix"), ("frontend:purchases", "purchases", "Minhas Compras"),
              ("frontend:profile", "profile", "Meu Perfil")]


@override_settings(FRONTEND_AUTH_LOCKED=True)
class AuthLockTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="11987654321", password="s3nha-forte")
        self.login_data = {"mobile": "11987654321", "password": "s3nha-forte"}

    @override_settings()
    def test_locked_by_default_when_setting_is_missing(self):
        from django.conf import settings
        del settings.FRONTEND_AUTH_LOCKED
        res = self.client.post(reverse("frontend:login"), self.login_data, **JSON)
        self.assertEqual(res.status_code, 503)

    def test_login_with_valid_credentials_is_refused_and_does_not_log_in(self):
        with mock.patch("frontend.forms.authenticate") as auth:
            res = self.client.post(reverse("frontend:login"), self.login_data, **JSON)
        self.assertEqual(res.status_code, 503)
        data = res.json()
        self.assertEqual((data["ok"], data["locked"], data["title"]),
                         (False, True, "Login temporariamente indisponível"))
        self.assertIn("O prazo de normalização é até 22h de hoje.", data["message"])
        auth.assert_not_called()
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_register_is_refused_and_creates_no_user(self):
        res = self.client.post(reverse("frontend:register"), VALID_REGISTRATION | {"phone": "(21) 91234-5678"}, **JSON)
        self.assertEqual(res.status_code, 503)
        self.assertEqual(res.json()["title"], "Cadastro temporariamente indisponível")
        self.assertFalse(get_user_model().objects.filter(username="21912345678").exists())
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_without_js_renders_page_with_notice_open(self):
        for name, title in (("frontend:login", "Login temporariamente"), ("frontend:register", "Cadastro temporariamente")):
            with self.subTest(name=name):
                res = self.client.post(reverse(name), self.login_data)
                self.assertEqual(res.status_code, 503)
                self.assertContains(res, 'id="authLockedModal" data-autoshow="0"', status_code=503)
                self.assertContains(res, title, status_code=503)
                self.assertNotContains(res, "s3nha-forte", status_code=503)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_pages_still_open_with_notice_ready_but_closed(self):
        for name in ("frontend:login", "frontend:register"):
            res = self.client.get(reverse(name))
            self.assertEqual(res.status_code, 200)
            self.assertContains(res, 'id="authLockedModal" role="dialog"')

    def test_csrf_still_enforced_while_locked(self):
        res = Client(enforce_csrf_checks=True).post(reverse("frontend:login"), self.login_data, **JSON)
        self.assertEqual(res.status_code, 403)

    @override_settings(FRONTEND_WHATSAPP_URL="", FRONTEND_TELEGRAM_URL="", FRONTEND_SUPPORT_URL="")
    def test_notice_has_community_buttons_from_admin(self):
        from django.core.cache import cache
        from .models import CommunicationChannels
        cache.clear()
        self.addCleanup(cache.clear)

        def notice(name):
            # Recorta só o aviso: o modal "Entre na comunidade" vem depois e tem os mesmos links.
            html = self.client.get(reverse(name)).content.decode()
            start = html.index('id="authLockedModal"')
            end = html.find('id="communityModal"', start)
            return html[start:end if end != -1 else None]

        # Sem links cadastrados: só o botão de fechar, sem botões de comunidade.
        self.assertNotIn("wl-btn-whats", notice("frontend:login"))
        self.assertIn(">Entendi</button>", notice("frontend:login"))

        CommunicationChannels.objects.create(community_whatsapp="https://chat.whatsapp.com/GRUPO",
                                             community_telegram="https://t.me/+CANAL")
        cache.clear()
        for name in ("frontend:login", "frontend:register"):
            modal = notice(name)
            self.assertIn('href="https://chat.whatsapp.com/GRUPO" target="_blank" rel="noopener noreferrer" '
                          'class="wl-btn-whats"', modal)
            self.assertIn('href="https://t.me/+CANAL" target="_blank" rel="noopener noreferrer" class="wl-btn-tele"',
                          modal)

    @override_settings(FRONTEND_AUTH_LOCKED=False)
    def test_unlocked_has_no_notice(self):
        for name in ("frontend:login", "frontend:register"):
            self.assertNotContains(self.client.get(reverse(name)), "authLockedModal")


class AppShellTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="11987654321", password="s3nha-forte")

    def test_anonymous_full_load_goes_to_login_with_next(self):
        res = self.client.get(reverse("frontend:team"))
        self.assertRedirects(res, reverse("frontend:login") + "?next=/equipe", fetch_redirect_response=False)

    def test_anonymous_spa_request_gets_401_with_login_url(self):
        # Sessão expirada no meio da navegação: o JS precisa de um sinal claro, não do HTML do login.
        res = self.client.get(reverse("frontend:team"), **SPA)
        self.assertEqual(res.status_code, 401)
        self.assertEqual(res.json(), {"ok": False, "redirect": reverse("frontend:login") + "?next=/equipe"})

    @override_settings(FRONTEND_AUTH_LOCKED=False)
    def test_login_lands_on_home(self):
        res = self.client.post(reverse("frontend:login"), {"mobile": "11987654321", "password": "s3nha-forte"})
        self.assertRedirects(res, reverse("frontend:home"))

    def test_each_tab_full_load_renders_shell_with_that_tab_active(self):
        self.client.force_login(self.user)
        for url_name, tab, label in APP_ROUTES:
            with self.subTest(tab=tab):
                res = self.client.get(reverse(url_name))
                self.assertEqual(res.status_code, 200)
                html = res.content.decode()
                self.assertIn(f"<title>{label} • New Tractors</title>", html)
                self.assertIn('class="app-tabbar"', html)
                self.assertIn('class="app-chat-fab"', html)
                # 5 abas na navbar + o logo do cabeçalho (volta ao Início sem reload).
                self.assertEqual(len(re.findall(r'class="app-tab[ "]', html)), 5)
                shell_only = re.sub(r'<main id="appView".*?</main>', "", html, flags=re.S)
                # + menu lateral do desktop: logo, "Depositar Saldo" e 5 itens.
                # + "Extrato" do menu lateral.
                self.assertEqual(shell_only.count("data-spa-link"), 13)
                self.assertRegex(html, r'class="app-header-logo" data-spa-link data-tab="home"')
                # Aba ativa marcada na navbar e no menu lateral (Depositar só existe na navbar).
                self.assertEqual(html.count('aria-current="page"'), 1 if tab == "deposit" else 2)
                self.assertRegex(html, rf'data-tab="{tab}"\s+class="app-tab[^"]*is-active')
                self.assertIn(f'data-page="{tab}"', html)

    def test_spa_request_returns_only_the_page_fragment(self):
        self.client.force_login(self.user)
        for url_name, tab, label in APP_ROUTES:
            with self.subTest(tab=tab):
                res = self.client.get(reverse(url_name), **SPA)
                self.assertEqual(res.status_code, 200)
                data = res.json()
                self.assertEqual((data["ok"], data["tab"], data["title"]), (True, tab, f"{label} • New Tractors"))
                self.assertIn(f'data-page="{tab}"', data["html"])
                # A casca não vem de novo: navbar e Chat ficam na página.
                self.assertNotIn("app-tabbar", data["html"])
                self.assertNotIn("app-chat-fab", data["html"])

    def test_shell_and_fragment_are_never_mixed_in_cache(self):
        self.client.force_login(self.user)
        for extra in ({}, SPA):
            res = self.client.get(reverse("frontend:home"), **extra)
            self.assertIn("X-SPA-Request", res["Vary"])
            self.assertIn("no-store", res["Cache-Control"])

    @override_settings(FRONTEND_WHATSAPP_URL="", FRONTEND_TELEGRAM_URL="", FRONTEND_SUPPORT_URL="")
    def test_chat_opens_support_modal_even_without_channels(self):
        self.client.force_login(self.user)
        html = self.client.get(reverse("frontend:home")).content.decode()
        self.assertIn('class="app-chat-fab" aria-label="Chat de atendimento" data-open-modal="supportModal"', html)
        self.assertIn('id="supportModal"', html)
        self.assertIn("Os canais de atendimento estão indisponíveis", html)

    @override_settings(FRONTEND_WHATSAPP_URL="https://wa.me/5511999999999", FRONTEND_TELEGRAM_URL="https://t.me/x",
                       FRONTEND_SUPPORT_URL="")
    def test_support_modal_lists_configured_channels(self):
        self.client.force_login(self.user)
        html = self.client.get(reverse("frontend:team")).content.decode()
        self.assertIn('href="https://wa.me/5511999999999" target="_blank" rel="noopener noreferrer" class="sp-channel is-whatsapp"', html)
        self.assertIn('href="https://t.me/x" target="_blank" rel="noopener noreferrer" class="sp-channel is-telegram"', html)
        for trigger in ('app-header-btn-support" aria-label="Suporte" data-open-modal="supportModal"',
                        'class="app-sidebar-action" data-open-modal="supportModal"'):
            self.assertIn(trigger, html)


class BrlFilterTests(TestCase):
    def test_formats_like_the_site(self):
        from decimal import Decimal

        from .templatetags.frontend_format import brl
        cases = {
            Decimal("15.2"): "R$ 15,20", Decimal("0"): "R$ 0,00", Decimal("5050"): "R$ 5.050,00",
            Decimal("1234567.891"): "R$ 1.234.567,89", Decimal("0.005"): "R$ 0,01", Decimal("-3"): "-R$ 3,00",
            "17.45": "R$ 17,45", None: "R$ 0,00", "abc": "R$ 0,00",
        }
        for value, expected in cases.items():
            with self.subTest(value=value):
                self.assertEqual(brl(value), expected)


def fake_wallet(user):
    from decimal import Decimal
    return {"invest_balance": Decimal("10.20"), "withdraw_balance": Decimal("5.00")}


def fake_header_unread(user):
    return {"has_unread_notifications": True}


class HomeAndHeaderTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="11987654321", password="s3nha-forte")
        self.client.force_login(self.user)

    @override_settings(FRONTEND_WALLET_PROVIDER="frontend.tests.fake_wallet")
    def test_home_shows_balances_and_total_is_the_sum(self):
        html = self.client.get(reverse("frontend:home")).content.decode()
        self.assertIn('<p class="home-wallet-total" data-wallet="total_balance">R$ 15,20</p>', html)
        self.assertEqual(html.count('<p class="home-balance-value"'), 2)
        self.assertIn('data-wallet="invest_balance">R$ 10,20</p>', html)
        self.assertIn('data-wallet="withdraw_balance">R$ 5,00</p>', html)

    @override_settings(FRONTEND_WALLET_PROVIDER="frontend.tests.fake_wallet")
    def test_home_spa_fragment_also_has_balances(self):
        data = self.client.get(reverse("frontend:home"), **SPA).json()
        self.assertIn("R$ 15,20", data["html"])

    @override_settings(FRONTEND_WALLET_PROVIDER=None)
    def test_without_provider_balances_are_zero(self):
        self.assertContains(self.client.get(reverse("frontend:home")), 'data-wallet="total_balance">R$ 0,00</p>')

    def test_header_is_in_the_shell_of_every_tab_but_not_in_fragments(self):
        for url_name, tab, _ in APP_ROUTES:
            with self.subTest(tab=tab):
                self.assertContains(self.client.get(reverse(url_name)), '<header class="app-header">')
                self.assertNotIn("app-header", self.client.get(reverse(url_name), **SPA).json()["html"])

    @override_settings(FRONTEND_HEADER_PROVIDER=None)
    def test_bell_dot_hidden_without_unread(self):
        self.assertNotContains(self.client.get(reverse("frontend:team")), "app-header-dot")

    @override_settings(FRONTEND_HEADER_PROVIDER="frontend.tests.fake_header_unread")
    def test_bell_dot_shown_with_unread(self):
        res = self.client.get(reverse("frontend:team"))
        self.assertContains(res, "app-header-dot")
        self.assertContains(res, 'aria-label="Notificações (há novas)"')

    @override_settings(FRONTEND_HEADER_PROVIDER="frontend.tests.fake_header_unread")
    def test_header_provider_is_not_called_on_spa_requests(self):
        with mock.patch("frontend.views.get_header_state") as provider:
            self.client.get(reverse("frontend:team"), **SPA)
        provider.assert_not_called()

def fake_checkin_done(user):
    return {"done_today": True}


class HomeCheckinTests(TestCase):
    def setUp(self):
        self.client.force_login(get_user_model().objects.create_user(username="11987654321", password="x"))

    @override_settings(FRONTEND_CHECKIN_PROVIDER=None)
    def test_pending_checkin_shows_button(self):
        res = self.client.get(reverse("frontend:home"))
        self.assertContains(res, "Fazer check-in")
        self.assertContains(res, "data-checkin-url=")
        self.assertNotContains(res, "Check-in realizado hoje")

    @override_settings(FRONTEND_CHECKIN_PROVIDER="frontend.tests.fake_checkin_done")
    def test_done_checkin_shows_status(self):
        res = self.client.get(reverse("frontend:home"))
        self.assertContains(res, "Check-in realizado hoje")
        self.assertNotContains(res, "Fazer check-in")

class ProductsAndSidebarTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="11987654321", password="x",
                                                         first_name="joao", last_name="lenon")
        self.client.force_login(self.user)

    def test_home_lists_all_12_machines_with_computed_total(self):
        html = self.client.get(reverse("frontend:home")).content.decode()
        self.assertEqual(html.count('<article class="home-product"'), 12)
        # NW354: diário 5 × 16 dias = 80; NWRT23K: 2.000 × 16 = 32.000
        self.assertIn('+R$ 5,00<small>/dia</small>', html)
        self.assertIn('<dd class="home-product-total">R$ 80,00</dd>', html)
        self.assertIn('<dd class="home-product-total">R$ 32.000,00</dd>', html)
        self.assertIn("R$ 10.000,00", html)

    @override_settings(FRONTEND_PRODUCTS_PROVIDER="frontend.tests.no_products")
    def test_empty_catalog_shows_message(self):
        self.assertContains(self.client.get(reverse("frontend:home")), "Nenhum equipamento disponível no momento.")

    def test_sidebar_shows_user_and_active_item(self):
        res = self.client.get(reverse("frontend:purchases"))
        self.assertContains(res, '<span class="app-sidebar-avatar" aria-hidden="true">JL</span>')
        self.assertContains(res, "<strong>joao lenon</strong>")
        self.assertRegex(res.content.decode(), r'class="app-side-link is-active" data-spa-link data-tab="purchases"')
        self.assertRegex(res.content.decode(), r'<a href="/extrato" class="app-side-link" data-spa-link data-tab="statement"')

    def test_logout_requires_post_and_ends_session(self):
        self.assertEqual(self.client.get(reverse("frontend:logout")).status_code, 405)
        res = self.client.post(reverse("frontend:logout"))
        self.assertRedirects(res, reverse("frontend:login"), fetch_redirect_response=False)
        self.assertNotIn("_auth_user_id", self.client.session)


def no_products(user):
    return []

# ---------------------------------------------------------------------------
# Ações do Início (check-in, bônus, roleta, compra)
# ---------------------------------------------------------------------------
CALLS = []


def fake_ok_checkin(user):
    return {"ok": True}


def fake_bonus(user, code):
    CALLS.append(("bonus", code))
    return {"ok": True, "amount": "2.6"} if code == "NEW2026" else {"ok": False, "message": "Código inválido ou já utilizado."}


def fake_spins_1(user):
    return {"spins_available": 1}


def fake_spin(user):
    return {"ok": True, "prize_amount": "10", "segment_index": 9}


def fake_purchase(user, product_id, idempotency_key):
    CALLS.append(("purchase", product_id, idempotency_key))
    return {"ok": True, "spins_awarded": 1}


def fake_purchase_no_balance(user, product_id, idempotency_key):
    return {"ok": False, "message": "Saldo insuficiente."}


def fake_boom(user):
    raise RuntimeError("detalhe interno secreto")


# As settings do preview ligam ações/dados de demonstração; aqui cada teste liga só o que precisa.
@override_settings(FRONTEND_CHECKIN_ACTION=None, FRONTEND_BONUS_ACTION=None, FRONTEND_ROULETTE_ACTION=None,
                   FRONTEND_PURCHASE_ACTION=None, FRONTEND_ROULETTE_PROVIDER=None, FRONTEND_WALLET_PROVIDER=None)
class HomeActionTests(TestCase):
    def setUp(self):
        CALLS.clear()
        self.user = get_user_model().objects.create_user(username="11987654321", password="x")
        self.client.force_login(self.user)

    def post(self, name, data=None, **extra):
        kwargs = {"product_id": extra.pop("product_id")} if "product_id" in extra else {}
        return self.client.post(reverse(name, kwargs=kwargs), data or {}, **extra)

    def test_requires_login_with_json_401(self):
        self.client.logout()
        res = self.post("frontend:action_checkin")
        self.assertEqual(res.status_code, 401)
        self.assertFalse(res.json()["ok"])

    def test_only_post_and_csrf_enforced(self):
        self.assertEqual(self.client.get(reverse("frontend:action_checkin")).status_code, 405)
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.user)
        self.assertEqual(csrf_client.post(reverse("frontend:action_checkin")).status_code, 403)

    def test_without_backend_action_is_unavailable_not_fake_success(self):
        res = self.post("frontend:action_checkin")
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["message"], "Função indisponível no momento. Tente novamente mais tarde.")

    @override_settings(FRONTEND_CHECKIN_ACTION="frontend.tests.fake_ok_checkin",
                       FRONTEND_WALLET_PROVIDER="frontend.tests.fake_wallet")
    def test_success_returns_updated_balances(self):
        data = self.post("frontend:action_checkin").json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["wallet"], {"total_balance": "R$ 15,20", "invest_balance": "R$ 10,20",
                                          "withdraw_balance": "R$ 5,00"})
        self.assertEqual(data["spins_available"], 0)

    @override_settings(FRONTEND_BONUS_ACTION="frontend.tests.fake_bonus")
    def test_bonus_normalizes_code_and_formats_amount(self):
        data = self.post("frontend:action_bonus", {"code": " new 2026 "}).json()
        self.assertEqual((data["ok"], data["amount"]), (True, "R$ 2,60"))
        self.assertEqual(CALLS, [("bonus", "NEW2026")])

    @override_settings(FRONTEND_BONUS_ACTION="frontend.tests.fake_bonus")
    def test_bonus_validation_and_business_error(self):
        self.assertEqual(self.post("frontend:action_bonus", {"code": ""}).json()["message"], "Informe o código.")
        self.assertEqual(self.post("frontend:action_bonus", {"code": "<script>"}).status_code, 400)
        self.assertEqual(self.post("frontend:action_bonus", {"code": "X" * 33}).status_code, 400)
        res = self.post("frontend:action_bonus", {"code": "ERRADO"})
        self.assertEqual((res.status_code, res.json()["message"]), (400, "Código inválido ou já utilizado."))
        self.assertEqual(CALLS, [("bonus", "ERRADO")])  # códigos inválidos nem chegam no backend

    @override_settings(FRONTEND_ROULETTE_ACTION="frontend.tests.fake_spin")
    def test_roulette_without_spins_is_refused_before_backend(self):
        res = self.post("frontend:action_roulette")
        self.assertEqual((res.status_code, res.json()["message"]), (400, "Você não tem giros disponíveis."))

    @override_settings(FRONTEND_ROULETTE_ACTION="frontend.tests.fake_spin",
                       FRONTEND_ROULETTE_PROVIDER="frontend.tests.fake_spins_1")
    def test_roulette_result_is_formatted_and_segment_bounded(self):
        data = self.post("frontend:action_roulette").json()
        self.assertEqual((data["prize_amount"], data["segment_index"]), ("R$ 10,00", 2))  # 9 % 7

    @override_settings(FRONTEND_PURCHASE_ACTION="frontend.tests.fake_purchase")
    def test_purchase_passes_product_and_idempotency_key(self):
        res = self.post("frontend:action_purchase", product_id="nw354", HTTP_X_IDEMPOTENCY_KEY="abc12345-key")
        self.assertEqual(res.json()["spins_awarded"], 1)
        self.assertEqual(CALLS, [("purchase", "nw354", "abc12345-key")])

    @override_settings(FRONTEND_PURCHASE_ACTION="frontend.tests.fake_purchase")
    def test_purchase_rejects_unknown_product_and_missing_key(self):
        self.assertEqual(self.post("frontend:action_purchase", product_id="nao-existe",
                                   HTTP_X_IDEMPOTENCY_KEY="abc12345-key").status_code, 404)
        self.assertEqual(self.post("frontend:action_purchase", product_id="nw354").status_code, 400)
        self.assertEqual(CALLS, [])

    @override_settings(FRONTEND_PURCHASE_ACTION="frontend.tests.fake_purchase_no_balance")
    def test_purchase_business_error_message(self):
        res = self.post("frontend:action_purchase", product_id="nw354", HTTP_X_IDEMPOTENCY_KEY="abc12345-key")
        self.assertEqual((res.status_code, res.json()["message"]), (400, "Saldo insuficiente."))

    @override_settings(FRONTEND_CHECKIN_ACTION="frontend.tests.fake_boom")
    def test_backend_exception_gives_generic_500_without_details(self):
        with self.assertLogs("frontend.views", level="ERROR"):
            res = self.post("frontend:action_checkin")
        self.assertEqual(res.status_code, 500)
        self.assertNotIn("secreto", res.content.decode())
        self.assertNotIn("Traceback", res.content.decode())

    @override_settings(FRONTEND_ROULETTE_PROVIDER="frontend.tests.fake_spins_1")
    def test_home_renders_modals_and_spin_count(self):
        html = self.client.get(reverse("frontend:home")).content.decode()
        for marker in ('id="rouletteModal"', 'data-spins="1"', 'id="bonusModal"', 'id="bonusSuccessModal"',
                       'id="purchaseSuccessModal"', 'id="actionErrorModal"', "data-purchase-url="):
            self.assertIn(marker, html)

def fake_profile_pix(user):
    return {"pix_linked": True}


class ProfileTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="82991028518", password="x",
                                                         first_name="Carlos Henrique", last_name="da Silva")
        self.client.force_login(self.user)

    def test_profile_lives_at_my_like_the_original_site(self):
        self.assertEqual(reverse("frontend:profile"), "/my")

    @override_settings(FRONTEND_PROFILE_PROVIDER=None, FRONTEND_WALLET_PROVIDER="frontend.tests.fake_wallet")
    def test_renders_account_wallet_and_menu(self):
        html = self.client.get(reverse("frontend:profile")).content.decode()
        self.assertIn('<h2 class="profile-name">Carlos Henrique da Silva</h2>', html)
        self.assertIn('<p class="profile-phone">(82) 99102-8518</p>', html)
        self.assertIn('data-wallet="invest_balance">R$ 10,20</p>', html)
        self.assertIn("avatar-padrao.jpg", html)
        for title in ("Fazer depósito", "Realizar saque", "Conta Pix", "Alterar senha", "Histórico de atividades",
                      "Meus investimentos", "Histórico de saques", "Suporte oficial", "Sobre a New Tractors"):
            self.assertIn(title, html)
        self.assertNotIn("✓ Vinculada", html)
        # Itens com tela pronta navegam pelo SPA.
        self.assertRegex(html, r'<a href="/recharge" data-spa-link data-tab="deposit" class="profile-menu-item"')
        self.assertRegex(html, r'<a href="/record" data-spa-link data-tab="purchases" class="profile-menu-item"')
        self.assertIn('action="/logout"', html)

    @override_settings(FRONTEND_PROFILE_PROVIDER="frontend.tests.fake_profile_pix")
    def test_pix_badge_when_linked(self):
        self.assertContains(self.client.get(reverse("frontend:profile")), "✓ Vinculada")

    def test_phone_filter(self):
        from .templatetags.frontend_format import phone_br
        self.assertEqual(phone_br("82991028518"), "(82) 99102-8518")
        self.assertEqual(phone_br("5582991028518"), "(82) 99102-8518")
        self.assertEqual(phone_br("8233334444"), "(82) 3333-4444")
        self.assertEqual(phone_br("admin"), "admin")

# ---------------------------------------------------------------------------
# Saque Pix
# ---------------------------------------------------------------------------
def fake_withdraw_state(user):
    from datetime import datetime, timezone as dt_tz
    from decimal import Decimal
    return {"pix_key": {"holder_name": "Carlos Henrique da Silva", "key_type": "phone", "key": "82991028518",
                        "document": "075.418.244-45"},
            "recent": [{"amount": Decimal("1000"), "created_at": datetime(2026, 9, 23, 13, 8, tzinfo=dt_tz.utc),
                        "status": "review"},
                       {"amount": Decimal("561.25"), "created_at": datetime(2026, 9, 19, 17, 10, tzinfo=dt_tz.utc),
                        "status": "paid"}]}


def fake_withdraw_nokey(user):
    return {"pix_key": None}


def fake_rich_wallet(user):
    from decimal import Decimal
    return {"invest_balance": Decimal("3.60"), "withdraw_balance": Decimal("45.25")}


def fake_withdraw_ok(user, amount, idempotency_key):
    CALLS.append(("withdraw", amount, idempotency_key))
    return {"ok": True}


def fake_withdraw_busy(user, amount, idempotency_key):
    return {"ok": False, "message": "Você já possui um saque em processamento. Aguarde a conclusão para solicitar outro."}


@override_settings(FRONTEND_WITHDRAW_PROVIDER="frontend.tests.fake_withdraw_state",
                   FRONTEND_WALLET_PROVIDER="frontend.tests.fake_rich_wallet",
                   FRONTEND_WITHDRAW_ACTION="frontend.tests.fake_withdraw_ok")
class WithdrawTests(TestCase):
    url = reverse("frontend:action_withdraw")
    KEY = {"HTTP_X_IDEMPOTENCY_KEY": "abc12345-key"}

    def setUp(self):
        CALLS.clear()
        self.user = get_user_model().objects.create_user(username="82991028518", password="x")
        self.client.force_login(self.user)

    def test_page_renders_key_fees_and_recent_list(self):
        html = self.client.get(reverse("frontend:withdraw")).content.decode()
        self.assertEqual(reverse("frontend:withdraw"), "/withdraw")
        for marker in ('data-balance-cents="4525"', 'data-min-cents="500"', 'data-fee-bp="1000"', 'data-has-key="1"',
                       "✓ Chave Vinculada", "Carlos Henrique da Silva", ">Telefone<", "075.418.244-45",
                       "10,0%", "Instantâneo", "- R$ 1.000,00", "Em revisão manual", "- R$ 561,25", ">Pago<",
                       "23/09/2026 10:08"):  # 13:08 UTC em São Paulo
            self.assertIn(marker, html)
        # Sub-tela do Perfil: a aba Perfil fica ativa na navbar.
        self.assertRegex(html, r'data-tab="profile"\s+class="app-tab[^"]*is-active')

    @override_settings(FRONTEND_WITHDRAW_PROVIDER="frontend.tests.fake_withdraw_nokey")
    def test_without_pix_key_page_asks_to_register_and_action_refuses(self):
        html = self.client.get(reverse("frontend:withdraw")).content.decode()
        self.assertIn("Nenhuma Chave Pix Cadastrada", html)
        self.assertIn('data-has-key="0"', html)
        res = self.client.post(self.url, {"amount": "10"}, **self.KEY)
        self.assertEqual((res.status_code, res.json()["message"]),
                         (400, "Cadastre sua chave Pix antes de solicitar saques."))
        self.assertEqual(CALLS, [])

    def test_amount_validation_happens_before_backend(self):
        cases = {"": "Informe um valor válido para o saque.", "abc": "Informe um valor válido para o saque.",
                 "-10": "Informe um valor válido para o saque.", "10.999": "Informe um valor válido para o saque.",
                 "4.99": "O valor mínimo para saque é R$ 5,00.", "45.26": "Saldo insuficiente para este saque."}
        for amount, message in cases.items():
            with self.subTest(amount=amount):
                res = self.client.post(self.url, {"amount": amount}, **self.KEY)
                self.assertEqual((res.status_code, res.json()["message"]), (400, message))
        self.assertEqual(CALLS, [])

    def test_success_passes_exact_decimal_and_key(self):
        from decimal import Decimal
        for raw in ("45.25", "45,25"):
            CALLS.clear()
            data = self.client.post(self.url, {"amount": raw}, **self.KEY).json()
            self.assertTrue(data["ok"])
            self.assertEqual(CALLS, [("withdraw", Decimal("45.25"), "abc12345-key")])
        self.assertEqual(data["withdraw_balance_cents"], 4525)
        self.assertIn("Saque Pix", data["recent_html"])
        self.assertEqual(data["message"], "Saque enviado com sucesso! Estamos aguardando a confirmação da transferência.")

    def test_missing_idempotency_key_is_refused(self):
        self.assertEqual(self.client.post(self.url, {"amount": "10"}).status_code, 400)
        self.assertEqual(CALLS, [])

    @override_settings(FRONTEND_WITHDRAW_ACTION="frontend.tests.fake_withdraw_busy")
    def test_backend_refusal_message_reaches_user(self):
        res = self.client.post(self.url, {"amount": "10"}, **self.KEY)
        self.assertEqual(res.status_code, 400)
        self.assertIn("saque em processamento", res.json()["message"])

    def test_requires_login_and_csrf(self):
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.user)
        self.assertEqual(csrf_client.post(self.url, {"amount": "10"}, **self.KEY).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.post(self.url, {"amount": "10"}, **self.KEY).status_code, 401)
        self.assertEqual(CALLS, [])

# ---------------------------------------------------------------------------
# Depósito Pix, CPF do titular e chave Pix de saque
# ---------------------------------------------------------------------------
VALID_CPF = "529.982.247-25"


def fake_deposit_no_cpf(user):
    return {"cpf_registered": False}


def fake_deposit_cpf(user):
    return {"cpf_registered": True, "cpf_masked": "***.982.247-**"}


def fake_cpf_action(user, cpf):
    CALLS.append(("cpf", cpf))
    return {"ok": True}


def fake_create_deposit(user, amount, idempotency_key):
    CALLS.append(("deposit", amount, idempotency_key))
    return {"ok": True, "charge_id": "abc123def456"}


def fake_charge(user, charge_id):
    from datetime import datetime, timezone as dt_tz
    from decimal import Decimal
    if charge_id != "abc123def456":
        return None
    return {"amount": Decimal("47"), "pix_code": "00020101021226900014br.gov.bcb.pix0136demo-code6304ABCD",
            "expires_at": datetime(2030, 1, 1, tzinfo=dt_tz.utc), "status": "pending"}


def fake_charge_with_js_image(user, charge_id):
    return {**fake_charge(user, "abc123def456"), "qr_image": "javascript:alert(1)"}


def fake_status_paid(user, charge_id, manual_check):
    CALLS.append(("status", charge_id, manual_check))
    return {"ok": True, "status": "paid"}


def fake_pix_key_action(user, key_type, key):
    CALLS.append(("pix", key_type, key))
    return {"ok": True}


@override_settings(FRONTEND_DEPOSIT_PROVIDER="frontend.tests.fake_deposit_cpf",
                   FRONTEND_DEPOSIT_CHARGE_PROVIDER="frontend.tests.fake_charge",
                   FRONTEND_CPF_ACTION="frontend.tests.fake_cpf_action",
                   FRONTEND_DEPOSIT_ACTION="frontend.tests.fake_create_deposit",
                   FRONTEND_DEPOSIT_STATUS="frontend.tests.fake_status_paid",
                   FRONTEND_PIX_KEY_ACTION="frontend.tests.fake_pix_key_action")
class DepositTests(TestCase):
    KEY = {"HTTP_X_IDEMPOTENCY_KEY": "abc12345-key"}

    def setUp(self):
        CALLS.clear()
        self.user = get_user_model().objects.create_user(username="11987654321", password="x")
        self.client.force_login(self.user)

    def test_cpf_validator(self):
        from .validators import cpf_is_valid
        self.assertTrue(cpf_is_valid("52998224725"))
        for bad in ("52998224724", "11111111111", "123", ""):
            self.assertFalse(cpf_is_valid(bad), bad)

    def test_recharge_page_with_presets_and_min(self):
        self.assertEqual(reverse("frontend:deposit"), "/recharge")
        html = self.client.get(reverse("frontend:deposit")).content.decode()
        for marker in ('data-preset-cents="5000"', 'data-preset-cents="200000"', ">R$ 1.000<", "Mínimo: <strong>R$ 25,00",
                       'data-min-cents="2500"', 'data-cpf-registered="1"', "***.982.247-**", 'id="cpfModal"'):
            self.assertIn(marker, html)

    @override_settings(FRONTEND_DEPOSIT_PROVIDER="frontend.tests.fake_deposit_no_cpf")
    def test_deposit_requires_cpf_first(self):
        res = self.client.post(reverse("frontend:action_deposit"), {"amount": "47"}, **self.KEY)
        self.assertEqual(res.status_code, 400)
        self.assertTrue(res.json()["need_cpf"])
        self.assertEqual(CALLS, [])

    def test_cpf_action_validates_and_normalizes(self):
        bad = self.client.post(reverse("frontend:action_cpf"), {"cpf": "111.111.111-11"}).json()
        self.assertEqual(set(bad["errors"]), {"cpf"})
        self.assertTrue(self.client.post(reverse("frontend:action_cpf"), {"cpf": VALID_CPF}).json()["ok"])
        self.assertEqual(CALLS, [("cpf", "52998224725")])

    def test_deposit_amount_rules(self):
        url = reverse("frontend:action_deposit")
        self.assertIn("mínimo", self.client.post(url, {"amount": "24.99"}, **self.KEY).json()["message"])
        self.assertIn("máximo", self.client.post(url, {"amount": "50000.01"}, **self.KEY).json()["message"])
        self.assertEqual(self.client.post(url, {"amount": "47"}).status_code, 400)  # sem chave de idempotência
        self.assertEqual(CALLS, [])

    def test_deposit_creates_charge_and_points_to_payment_page(self):
        from decimal import Decimal
        data = self.client.post(reverse("frontend:action_deposit"), {"amount": "47"}, **self.KEY).json()
        self.assertEqual(data["redirect"], "/recharge/abc123def456")
        self.assertEqual(CALLS, [("deposit", Decimal("47"), "abc12345-key")])

    def test_payment_page_renders_qr_and_code(self):
        html = self.client.get("/recharge/abc123def456").content.decode()
        self.assertIn("R$ 47,00", html)
        self.assertIn("demo-code6304ABCD", html)
        self.assertIn('src="data:image/svg+xml;base64,', html)  # QR gerado a partir do copia e cola
        self.assertIn('data-expires="2030-01-01T00:00:00+00:00"', html)
        # Aba Depositar ativa na navbar.
        self.assertRegex(html, r'data-tab="deposit"\s+class="app-tab[^"]*is-active')

    def test_payment_page_of_unknown_charge_is_404(self):
        self.assertEqual(self.client.get("/recharge/naoexiste99").status_code, 404)

    @override_settings(FRONTEND_DEPOSIT_CHARGE_PROVIDER="frontend.tests.fake_charge_with_js_image")
    def test_unsafe_qr_image_from_provider_is_ignored(self):
        html = self.client.get("/recharge/abc123def456").content.decode()
        self.assertNotIn("javascript:", html)
        self.assertIn('src="data:image/svg+xml;base64,', html)

    def test_status_paid_redirects_to_profile(self):
        data = self.client.post(reverse("frontend:action_deposit_status", args=["abc123def456"]), {"manual": "1"}).json()
        self.assertEqual((data["status"], data["redirect"]), ("paid", "/my"))
        self.assertEqual(CALLS, [("status", "abc123def456", True)])

    def test_pix_key_action_validates_per_type(self):
        url = reverse("frontend:action_pix_key")
        for data in ({"key_type": "phone", "key": "(11) 9876-5432"}, {"key_type": "email", "key": "sem-arroba"},
                     {"key_type": "random", "key": "123"}, {"key_type": "banana", "key": "x"},
                     {"key_type": "cnpj", "key": "11.222.333/0001-80"}, {"key_type": "cpf", "key": "000"}):
            with self.subTest(data=data):
                res = self.client.post(url, data)
                self.assertEqual(res.status_code, 400)
                self.assertIn("key", res.json()["errors"])
        self.assertEqual(CALLS, [])
        self.assertTrue(self.client.post(url, {"key_type": "phone", "key": "+55 (11) 98765-4321"}).json()["ok"])
        self.assertTrue(self.client.post(url, {"key_type": "cnpj", "key": "11.222.333/0001-81"}).json()["ok"])
        self.assertEqual(CALLS, [("pix", "phone", "11987654321"), ("pix", "cnpj", "11222333000181")])

    def test_actions_require_csrf(self):
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.user)
        for name in ("frontend:action_cpf", "frontend:action_deposit", "frontend:action_pix_key"):
            self.assertEqual(csrf_client.post(reverse(name), {}).status_code, 403)
        self.assertEqual(CALLS, [])

# ---------------------------------------------------------------------------
# Minhas Compras
# ---------------------------------------------------------------------------
def fake_contracts(user):
    from datetime import timedelta
    from decimal import Decimal
    from django.utils import timezone
    now = timezone.now()
    return [
        {"contract_id": 33832, "product_id": "nw4050", "code": "NW4050", "amount": Decimal("50"),
         "daily_credit": Decimal("10"), "started_at": now, "ends_at": now + timedelta(days=16),
         "accumulated": Decimal("10"), "next_credit_at": now + timedelta(hours=18, minutes=24, seconds=30),
         "status": "active"},
        {"contract_id": 20850, "product_id": "nw354", "code": "NW354", "amount": Decimal("25"),
         "daily_credit": Decimal("5"), "started_at": now, "ends_at": now + timedelta(days=16),
         "accumulated": Decimal("10"), "next_credit_at": None, "status": "finished"},
    ]


class PurchasesTests(TestCase):
    def setUp(self):
        self.client.force_login(get_user_model().objects.create_user(username="11987654321", password="x"))

    def test_lives_at_record(self):
        self.assertEqual(reverse("frontend:purchases"), "/record")

    @override_settings(FRONTEND_PURCHASES_PROVIDER="frontend.tests.fake_contracts")
    def test_summary_counts_only_active_and_lists_contracts(self):
        html = self.client.get(reverse("frontend:purchases")).content.decode()
        self.assertIn('<p class="pc-stat-value">R$ 50,00</p>', html)          # só o ativo
        self.assertIn("+R$ 10,00<small>/dia</small>", html)
        self.assertIn("<strong>1</strong> equipamentos ativos", html)
        self.assertIn('<strong class="is-gold">R$ 20,00</strong>', html)       # lucro de todos
        self.assertIn("Contrato #33832", html)
        self.assertIn("18h 24min", html)
        self.assertIn("produtos/nw4050.jpg", html)                              # foto do catálogo
        self.assertIn(">Finalizado</span>", html)

    @override_settings(FRONTEND_PURCHASES_PROVIDER=None)
    def test_empty_state(self):
        html = self.client.get(reverse("frontend:purchases")).content.decode()
        self.assertIn("Nenhum equipamento ativo no momento", html)
        self.assertIn('<p class="pc-stat-value">R$ 0,00</p>', html)

    def test_countdown_never_negative(self):
        from datetime import timedelta
        from django.utils import timezone
        from .views import countdown_label
        now = timezone.now()
        self.assertEqual(countdown_label(now + timedelta(hours=22, minutes=4, seconds=59), now), "22h 04min")
        self.assertEqual(countdown_label(now - timedelta(hours=1), now), "0h 00min")
        self.assertEqual(countdown_label(None), "—")

# ---------------------------------------------------------------------------
# Extrato (modal) e ativação de equipamento
# ---------------------------------------------------------------------------
STATEMENT_CALLS = []


def fake_statement(user, kinds, offset, limit):
    from datetime import timedelta
    from decimal import Decimal
    from django.utils import timezone
    STATEMENT_CALLS.append((kinds, offset, limit))
    now = timezone.now()
    rows = [{"id": i, "kind": "commission", "title": "Comissão por Indicação",
             "description": "Bônus referente à sua equipe", "amount": Decimal("0.50"),
             "created_at": now - timedelta(minutes=i), "status": "completed"} for i in range(25)]
    rows.append({"id": 99, "kind": "withdraw", "title": "Saque PIX para Conta", "description": "Em análise",
                 "amount": Decimal("-1000"), "created_at": now - timedelta(days=9), "status": "processing"})
    return rows[offset:offset + limit]


@override_settings(FRONTEND_STATEMENT_PROVIDER="frontend.tests.fake_statement")
class StatementTests(TestCase):
    url = reverse("frontend:statement")

    def setUp(self):
        STATEMENT_CALLS.clear()
        self.client.force_login(get_user_model().objects.create_user(username="11987654321", password="x"))

    def test_first_page_and_pagination(self):
        first = self.client.get(self.url).json()
        self.assertTrue(first["has_more"])
        self.assertEqual((first["next_offset"], first["html"].count('class="st-item"')), (20, 20))
        self.assertIn("Hoje, ", first["html"])
        self.assertIn("+R$ 0,50", first["html"])
        second = self.client.get(self.url, {"offset": 20}).json()
        self.assertFalse(second["has_more"])
        self.assertIn("-R$ 1.000,00", second["html"])
        self.assertIn(">Processando<", second["html"])
        self.assertEqual(STATEMENT_CALLS[0], (None, 0, 21))  # pede um a mais para saber se há próxima página

    def test_filter_maps_to_kinds_and_bad_input_is_safe(self):
        self.client.get(self.url, {"filtro": "income"})
        self.client.get(self.url, {"filtro": "hack", "offset": "-5"})
        self.client.get(self.url, {"offset": "abc"})
        self.client.get(self.url, {"offset": "999999999"})
        self.assertEqual(STATEMENT_CALLS[0][0], {"yield", "checkin", "commission", "bonus"})
        self.assertEqual(STATEMENT_CALLS[1], (None, 0, 21))
        self.assertEqual(STATEMENT_CALLS[2], (None, 0, 21))
        self.assertEqual(STATEMENT_CALLS[3][1], 5000)

    @override_settings(FRONTEND_STATEMENT_PROVIDER=None)
    def test_empty(self):
        self.assertIn("Nenhuma movimentação", self.client.get(self.url).json()["html"])

    def test_requires_login(self):
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 401)

    def test_modal_and_triggers_are_in_shell_and_old_page_is_gone(self):
        html = self.client.get(reverse("frontend:home")).content.decode()
        self.assertIn('id="statementModal"', html)
        for key in ("all", "income", "roulette", "deposit", "withdraw"):
            self.assertIn(f'data-statement-filter="{key}"', html)
        self.assertIn('class="home-action" data-open-statement="all"', html)
        self.assertEqual(reverse("frontend:statement_page"), "/extrato")

    def test_day_label(self):
        from datetime import timedelta
        from django.utils import timezone
        from .templatetags.frontend_format import day_label, signed_brl
        now = timezone.localtime()
        self.assertTrue(day_label(now).startswith("Hoje, "))
        self.assertTrue(day_label(now - timedelta(days=1)).startswith("Ontem, "))
        self.assertRegex(day_label(now - timedelta(days=5)), r"^\d{2}/\d{2}/\d{4}, \d{2}:\d{2}$")
        self.assertEqual((signed_brl(5), signed_brl(-5), signed_brl(0)), ("+R$ 5,00", "-R$ 5,00", "R$ 0,00"))


class ActivationTests(TestCase):
    def setUp(self):
        self.client.force_login(get_user_model().objects.create_user(username="11987654321", password="x"))

    @override_settings(FRONTEND_WALLET_PROVIDER="frontend.tests.fake_wallet")
    def test_product_buttons_carry_values_in_cents(self):
        html = self.client.get(reverse("frontend:home")).content.decode()
        self.assertIn('data-invest-cents="1020"', html)
        self.assertIn('id="activateModal"', html)
        self.assertRegex(html, r'data-code="NW354"\s+data-price-cents="2500" data-daily-cents="500"\s+'
                               r'data-total-cents="8000" data-days="16"')

    @override_settings(FRONTEND_WALLET_PROVIDER="frontend.tests.fake_wallet",
                       FRONTEND_PURCHASE_ACTION="frontend.tests.fake_purchase")
    def test_purchase_response_has_invest_cents(self):
        res = self.client.post(reverse("frontend:action_purchase", args=["nw354"]),
                               HTTP_X_IDEMPOTENCY_KEY="abc12345-key").json()
        self.assertEqual(res["invest_balance_cents"], 1020)

# ---------------------------------------------------------------------------
# Equipe
# ---------------------------------------------------------------------------
def fake_team(user):
    from datetime import datetime, timezone as dt_tz
    from decimal import Decimal
    day = datetime(2026, 9, 19, 12, tzinfo=dt_tz.utc)
    return {
        "invite_code": "2LK7QX", "commissions_total": Decimal("30.25"),
        "levels": [{"level": 1, "percent": 18, "members": 2, "active": 1, "volume": 25, "credited": "4.5"},
                   {"level": 2, "percent": 2, "members": 6, "active": 4, "volume": 175, "credited": "3.5"},
                   {"level": 3, "percent": 1, "members": 9, "active": 4, "volume": 2225, "credited": "22.25"}],
        "members": [{"name": "<b>MARIA</b>", "phone": "66997127059", "joined_at": day, "level": 1, "active": True,
                     "invested": 25}],
        "goals": [{"prize": 10, "invites_done": 1, "invites_target": 1, "volume_done": 7025, "volume_target": 100,
                   "status": "claimed", "claimed_at": day},
                  {"prize": 50, "invites_done": 20, "invites_target": 30, "volume_done": 7025, "volume_target": 8000,
                   "status": "in_progress", "claimed_at": None}],
    }


@override_settings(FRONTEND_TEAM_PROVIDER="frontend.tests.fake_team")
class TeamTests(TestCase):
    def setUp(self):
        self.client.force_login(get_user_model().objects.create_user(username="11987654321", password="x"))

    def test_summary_is_computed_from_levels(self):
        html = self.client.get(reverse("frontend:team")).content.decode()
        self.assertIn('<p class="pc-stat-value">R$ 30,25</p>', html)
        self.assertIn("<strong>17</strong> membros", html)
        self.assertIn("<strong>9 ativos</strong>", html)
        self.assertIn("<strong>53%</strong>", html)                      # 9/17
        self.assertIn('<p class="tm-volume">R$ 2.425,00</p>', html)
        self.assertIn("1º Nível (Diretos)", html)
        self.assertIn('<strong class="tm-level-pct">18%</strong>', html)
        self.assertIn("<strong>6 (4 ativos)</strong>", html)

    def test_invite_link_and_whatsapp(self):
        html = self.client.get(reverse("frontend:team")).content.decode()
        self.assertIn("http://testserver/reg?code=2LK7QX", html)
        self.assertIn('href="https://wa.me/?text=Venha%20fazer%20parte', html)

    def test_members_escape_html_and_format_phone(self):
        html = self.client.get(reverse("frontend:team")).content.decode()
        self.assertIn("&lt;b&gt;MARIA&lt;/b&gt;", html)
        self.assertNotIn("<b>MARIA</b>", html)
        self.assertIn("(66) 99712-7059", html)
        self.assertIn('data-member-filter="3"', html)

    def test_goals_progress_and_missing(self):
        html = self.client.get(reverse("frontend:team")).content.decode()
        self.assertIn("Prêmio resgatado em 19/09/2026", html)
        self.assertIn('aria-valuenow="66"', html)                         # 20/30
        self.assertIn('aria-valuenow="87"', html)                         # 7025/8000
        self.assertIn('style="width: 100%"', html)                        # volume acima da meta não passa de 100%
        self.assertIn("Faltam <strong>10 convidados</strong> e <strong>R$ 975,00</strong>", html)

    def test_goals_tab_from_query(self):
        html = self.client.get(reverse("frontend:team"), {"aba": "metas"}).content.decode()
        self.assertRegex(html, r'data-team-panel="team"\s+hidden')
        self.assertNotRegex(html, r'data-team-panel="goals"\s+hidden')

    @override_settings(FRONTEND_TEAM_PROVIDER=None)
    def test_empty_team(self):
        html = self.client.get(reverse("frontend:team")).content.decode()
        self.assertIn("Você ainda não tem indicados", html)
        self.assertIn("<strong>0%</strong>", html)
        self.assertNotIn('class="tm-whats"', html)  # sem código de convite, sem botão de compartilhar

# ---------------------------------------------------------------------------
# Notificações, Extrato consolidado e Histórico de Saques
# ---------------------------------------------------------------------------
def fake_notifications(user, offset, limit):
    from datetime import timedelta
    from django.utils import timezone
    now = timezone.now()
    return [
        {"id": 1, "title": "Recompensa diária disponível!", "body": "Seu bônus...", "created_at": now,
         "read": False, "time_label": "Hoje"},
        {"id": 2, "title": "Rendimentos creditados com sucesso!", "body": "<script>x</script>",
         "created_at": now - timedelta(minutes=19), "read": True},
        {"id": 3, "title": "Saque PIX Transferido com Sucesso", "body": "Transferência...",
         "created_at": now - timedelta(hours=23), "read": True},
    ][offset:offset + limit]


def fake_read_all(user):
    CALLS.append(("read_all",))
    return {"ok": True}


def fake_summary(user):
    return {"count": 83, "income_total": "282.20", "deposit_total": "216",
            "counts": {"all": 83, "income": 70, "roulette": 4, "deposit": 4, "withdraw": 0}}


def fake_withdraw_history(user):
    from datetime import datetime, timezone as dt_tz
    day = datetime(2026, 9, 21, 21, 37, tzinfo=dt_tz.utc)
    return [{"id": 106812, "amount": 50, "fee": 5, "net": 45, "created_at": day, "settled_at": day, "status": "paid"},
            {"id": 56370, "amount": 30, "fee": 3, "net": 27, "created_at": day, "settled_at": None, "status": "review"}]


@override_settings(FRONTEND_NOTIFICATIONS_PROVIDER="frontend.tests.fake_notifications",
                   FRONTEND_NOTIFICATIONS_READ_ACTION="frontend.tests.fake_read_all",
                   FRONTEND_STATEMENT_SUMMARY_PROVIDER="frontend.tests.fake_summary",
                   FRONTEND_STATEMENT_PROVIDER="frontend.tests.fake_statement",
                   FRONTEND_WITHDRAW_HISTORY_PROVIDER="frontend.tests.fake_withdraw_history")
class FinalScreensTests(TestCase):
    def setUp(self):
        CALLS.clear()
        self.client.force_login(get_user_model().objects.create_user(username="11987654321", password="x"))

    def test_notifications_list_relative_time_and_escaping(self):
        data = self.client.get(reverse("frontend:notifications")).json()
        self.assertEqual(data["unread"], 1)
        self.assertIn('class="nf-item is-unread"', data["html"])
        self.assertIn(">Hoje<", data["html"])
        self.assertIn(">Há 19 min<", data["html"])
        self.assertIn(">Há 23 horas<", data["html"])
        self.assertIn("&lt;script&gt;", data["html"])

    def test_mark_all_read_requires_post_and_csrf(self):
        url = reverse("frontend:notifications_read")
        self.assertEqual(self.client.get(url).status_code, 405)
        self.assertTrue(self.client.post(url).json()["ok"])
        self.assertEqual(CALLS, [("read_all",)])
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(get_user_model().objects.get(username="11987654321"))
        self.assertEqual(csrf_client.post(url).status_code, 403)

    def test_bell_opens_panel(self):
        html = self.client.get(reverse("frontend:home")).content.decode()
        self.assertIn("app-header-btn-bell\" data-open-notifications", html)
        self.assertIn('id="notifModal"', html)

    def test_ago_filter(self):
        from datetime import timedelta
        from django.utils import timezone
        from .templatetags.frontend_format import ago
        now = timezone.now()
        self.assertEqual(ago(now), "Agora")
        self.assertEqual(ago(now - timedelta(hours=1, minutes=5)), "Há 1 hora")
        self.assertEqual(ago(now - timedelta(hours=5)), "Há 5 horas")
        self.assertRegex(ago(now - timedelta(days=9)), r"^\d{2}/\d{2}/\d{4}$")

    def test_statement_page_summary_and_filters(self):
        html = self.client.get(reverse("frontend:statement_page")).content.decode()
        for marker in ("Voltar ao Perfil", 'data-open-statement="all"', "<dd>83</dd>", "R$ 282,20", "R$ 216,00",
                       ">Todos (83)<", ">Roleta (4)<", ">Saques<", 'data-layout="page"'):
            self.assertIn(marker, html)

    def test_statement_page_layout_items(self):
        html = self.client.get(reverse("frontend:statement"), {"offset": 20, "layout": "page"}).json()["html"]
        self.assertIn('class="hs-item"', html)
        self.assertIn(">Saque Pix<", html)
        self.assertIn(">Transferência Pix<", html)
        self.assertIn("- R$ 1.000,00", html)

    def test_withdraw_history_page(self):
        html = self.client.get(reverse("frontend:withdraw_history")).content.decode()
        self.assertEqual(reverse("frontend:withdraw_history"), "/withdraw/history")
        for marker in ("Voltar ao Saque", "Saque Pix <small>#106812</small>", "- R$ 50,00", "✓ Pago",
                       "Líquido recebido", "R$ 45,00", ">Todos (2)<", ">Concluídos (1)<", ">Processando (1)<",
                       ">Cancelados/Outros<", "Aguardando liquidação", "<dd>R$ 45,00</dd>"):
            self.assertIn(marker, html)

    def test_profile_and_withdraw_link_to_new_pages(self):
        self.assertRegex(self.client.get(reverse("frontend:profile")).content.decode(),
                         r'<a href="/withdraw/history" data-spa-link data-tab="profile" class="profile-menu-item"')
        self.assertContains(self.client.get(reverse("frontend:withdraw")), 'href="/withdraw/history" class="wd-recent-all"')


# ---------------------------------------------------------------------------
# Suporte, senha, processo seletivo, check-in com recompensa
# ---------------------------------------------------------------------------
def fake_checkin_amount(user):
    return {"ok": True, "amount": "0.5"}


def fake_recruit(user, message):
    CALLS.append(("recruit", message))
    return {"ok": True}


class ExtrasTests(TestCase):
    def setUp(self):
        CALLS.clear()
        self.user = get_user_model().objects.create_user(username="11987654321", password="senha-antiga")
        self.client.force_login(self.user)

    def test_cnpj_validator(self):
        from .validators import cnpj_is_valid
        self.assertTrue(cnpj_is_valid("11222333000181"))
        for bad in ("11222333000180", "11111111111111", "123"):
            self.assertFalse(cnpj_is_valid(bad), bad)

    @override_settings(FRONTEND_CHECKIN_ACTION="frontend.tests.fake_checkin_amount")
    def test_checkin_returns_formatted_amount_and_modal_exists(self):
        self.assertEqual(self.client.post(reverse("frontend:action_checkin")).json()["amount"], "R$ 0,50")
        self.assertContains(self.client.get(reverse("frontend:home")), 'id="checkinSuccessModal"')

    def test_password_change_validations(self):
        url = reverse("frontend:action_password")
        bad = self.client.post(url, {"current_password": "errada", "new_password": "123",
                                     "new_password_confirmation": "999"}).json()
        self.assertEqual(bad["errors"]["current_password"], "Senha atual incorreta.")
        self.assertIn("mínimo 6", bad["errors"]["new_password"])
        mismatch = self.client.post(url, {"current_password": "senha-antiga", "new_password": "nova-senha-1",
                                          "new_password_confirmation": "outra"}).json()
        self.assertEqual(mismatch["errors"], {"new_password_confirmation": "As senhas não coincidem."})
        same = self.client.post(url, {"current_password": "senha-antiga", "new_password": "senha-antiga",
                                      "new_password_confirmation": "senha-antiga"}).json()
        self.assertIn("diferente", same["errors"]["new_password"])
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("senha-antiga"))

    def test_password_change_success_keeps_session(self):
        res = self.client.post(reverse("frontend:action_password"), {
            "current_password": "senha-antiga", "new_password": "nova-senha-1", "new_password_confirmation": "nova-senha-1"})
        self.assertTrue(res.json()["ok"])
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("nova-senha-1"))
        self.assertEqual(self.client.get(reverse("frontend:profile")).status_code, 200)  # continua logado

    def test_profile_items_open_modals(self):
        html = self.client.get(reverse("frontend:profile")).content.decode()
        for modal in ("passwordModal", "supportModal", "aboutModal"):
            self.assertIn(f'data-open-modal="{modal}" class="profile-menu-item"', html)
        self.assertIn('id="passwordModal"', html)
        self.assertIn("Nossa missão", html)

    @override_settings(FRONTEND_RECRUIT_ACTION="frontend.tests.fake_recruit")
    def test_recruit(self):
        self.assertContains(self.client.get(reverse("frontend:home")), 'class="home-recruit-btn" data-open-modal="recruitModal"')
        url = reverse("frontend:action_recruit")
        self.assertEqual(self.client.post(url, {"message": "x" * 501}).status_code, 400)
        self.assertTrue(self.client.post(url, {"message": "  Tenho experiência  "}).json()["ok"])
        self.assertEqual(CALLS, [("recruit", "Tenho experiência")])

    def test_new_actions_require_csrf(self):
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.user)
        for name in ("frontend:action_password", "frontend:action_recruit"):
            self.assertEqual(csrf_client.post(reverse(name), {}).status_code, 403)


# ---------------------------------------------------------------------------
# Links pelo admin + modais automáticos
# ---------------------------------------------------------------------------
@override_settings(FRONTEND_WHATSAPP_URL="", FRONTEND_TELEGRAM_URL="", FRONTEND_SUPPORT_URL="")
class ChannelsAndWelcomeTests(TestCase):
    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        self.user = get_user_model().objects.create_user(username="11987654321", password="x")

    def tearDown(self):
        from django.core.cache import cache
        cache.clear()

    def set_channels(self, **values):
        from .models import CommunicationChannels
        obj = CommunicationChannels(**values)
        obj.full_clean()
        obj.save()
        return obj

    def test_url_validators(self):
        from django.core.exceptions import ValidationError
        from .models import CommunicationChannels
        for field, bad in (("support_whatsapp", "http://wa.me/5511"), ("support_whatsapp", "https://evil.com/wa.me"),
                           ("community_telegram", "javascript:alert(1)"), ("community_telegram", "https://wa.me/x")):
            with self.subTest(field=field, bad=bad), self.assertRaises(ValidationError):
                CommunicationChannels(**{field: bad}).full_clean()
        CommunicationChannels(support_whatsapp="https://wa.me/5511999999999",
                              community_whatsapp="https://chat.whatsapp.com/ABC",
                              community_telegram="https://t.me/+XYZ").full_clean()

    def test_singleton(self):
        self.set_channels(support_whatsapp="https://wa.me/1")
        self.set_channels(support_whatsapp="https://wa.me/2")
        from .models import CommunicationChannels
        self.assertEqual(CommunicationChannels.objects.count(), 1)
        self.assertEqual(CommunicationChannels.objects.get().support_whatsapp, "https://wa.me/2")

    def test_admin_links_reach_support_modal_and_welcome_community(self):
        self.set_channels(support_whatsapp="https://wa.me/5511888887777", support_telegram="https://t.me/suporte_nt",
                          community_whatsapp="https://chat.whatsapp.com/GRUPO", community_telegram="https://t.me/+CANAL")
        self.client.force_login(self.user)
        html = self.client.get(reverse("frontend:home")).content.decode()
        self.assertIn('href="https://wa.me/5511888887777" target="_blank" rel="noopener noreferrer" class="sp-channel is-whatsapp"', html)
        self.assertIn('href="https://t.me/suporte_nt"', html)
        self.assertIn('href="https://chat.whatsapp.com/GRUPO" target="_blank" rel="noopener noreferrer" class="wl-btn-whats"', html)
        self.assertIn('href="https://t.me/+CANAL"', html)

    def test_saving_in_admin_invalidates_cache(self):
        from .channels import get_channels
        self.assertEqual(get_channels()["community_whatsapp"], "")
        self.set_channels(community_whatsapp="https://chat.whatsapp.com/NOVO")
        self.assertEqual(get_channels()["community_whatsapp"], "https://chat.whatsapp.com/NOVO")

    def test_welcome_and_share_on_full_load_only(self):
        self.client.force_login(self.user)
        html = self.client.get(reverse("frontend:purchases")).content.decode()
        self.assertIn('id="welcomeModal" data-autoshow="1"', html)
        self.assertIn('id="shareModal" data-autoshow="2"', html)
        self.assertIn("banner-compartilhe-ganhe.jpg", html)
        self.assertIn("#plataformanewtractors", html)  # texto do banner no alt (leitor de tela)
        self.assertNotIn("Comunidade New Tractors", html)  # sem links de comunidade, sem a seção
        spa = self.client.get(reverse("frontend:purchases"), **SPA).json()["html"]
        self.assertNotIn("welcomeModal", spa)

    def test_community_modal_on_login_and_register_only_when_configured(self):
        for name in ("frontend:login", "frontend:register"):
            self.assertNotContains(self.client.get(reverse(name)), 'id="communityModal"')
        self.set_channels(community_telegram="https://t.me/+CANAL")
        for name in ("frontend:login", "frontend:register"):
            res = self.client.get(reverse(name))
            self.assertContains(res, 'id="communityModal" data-autoshow="1"')
            self.assertContains(res, 'href="https://t.me/+CANAL"')
            self.assertNotContains(res, "class=\"wl-btn-whats\"")

    def test_admin_goes_straight_to_the_single_record(self):
        admin_user = get_user_model().objects.create_superuser(username="admin", password="x", email="a@a.a")
        self.client.force_login(admin_user)
        url = reverse("admin:frontend_communicationchannels_changelist")
        self.assertRedirects(self.client.get(url), reverse("admin:frontend_communicationchannels_add"))
        self.set_channels(support_whatsapp="https://wa.me/1")
        self.assertRedirects(self.client.get(url), reverse("admin:frontend_communicationchannels_change", args=[1]))

# Bloqueio temporário: só o Início (e as ações dele) responde; o resto é fechado por padrão no servidor.
HOME_ONLY_BLOCKED_PAGES = [("frontend:team", {}), ("frontend:deposit", {}),
                           ("frontend:deposit_payment", {"charge_id": "abc123"}), ("frontend:purchases", {}),
                           ("frontend:profile", {}), ("frontend:statement_page", {}), ("frontend:withdraw", {}),
                           ("frontend:withdraw_history", {})]
HOME_ONLY_BLOCKED_ACTIONS = [("frontend:action_withdraw", {}), ("frontend:action_cpf", {}),
                             ("frontend:action_deposit", {}), ("frontend:action_deposit_status", {"charge_id": "abc123"}),
                             ("frontend:action_pix_key", {}), ("frontend:action_password", {})]
HOME_ONLY_OPEN_ACTIONS = [("frontend:action_checkin", {}), ("frontend:action_bonus", {}),
                          ("frontend:action_roulette", {}), ("frontend:action_recruit", {}),
                          ("frontend:action_purchase", {"product_id": "t1"}), ("frontend:notifications_read", {})]


@override_settings(FRONTEND_ONLY_HOME=True)
class HomeOnlyTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="11987654321", password="s3nha-forte")
        self.client.force_login(self.user)

    def test_home_still_opens_with_lock_notice_ready(self):
        res = self.client.get(reverse("frontend:home"))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, 'id="areaLockedModal" role="dialog"')
        self.assertContains(res, "Área temporariamente indisponível")
        self.assertContains(res, "frontend/js/lock.js")

    def test_other_tabs_and_home_shortcuts_are_marked_locked(self):
        html = self.client.get(reverse("frontend:home")).content.decode()
        # Navbar: as 4 abas fora o Início; menu lateral: "Depositar Saldo" + 4 itens; Início: Depositar, Sacar, Extrato.
        self.assertEqual(len(re.findall(r'class="app-tab[^"]*is-locked"', html)), 4)
        self.assertEqual(len(re.findall(r'class="app-side-link[^"]*is-locked"', html)), 4)
        self.assertIn('class="app-sidebar-deposit is-locked"', html)
        self.assertEqual(len(re.findall(r'class="home-action[^"]*is-locked"', html)), 3)
        self.assertRegex(html, r'data-tab="home"\s+class="app-tab is-active"\s+aria-current="page">')
        self.assertNotRegex(html, r'data-tab="home"[^>]*data-locked')
        # Links para áreas fechadas dentro dos modais do Início (depósito na ativação, "Ver Minhas Compras").
        self.assertEqual(html.count('is-locked-inline'), 3)
        # Cada elemento marcado abre o aviso (lock.js) e é anunciado como indisponível.
        self.assertEqual(html.count(" data-locked"), html.count('aria-disabled="true"'))

    def test_blocked_pages_redirect_to_home_on_full_load_and_spa(self):
        for name, kwargs in HOME_ONLY_BLOCKED_PAGES:
            for extra in ({}, SPA):
                with self.subTest(page=name, spa=bool(extra)):
                    res = self.client.get(reverse(name, kwargs=kwargs), **extra)
                    self.assertRedirects(res, reverse("frontend:home"), fetch_redirect_response=False)

    def test_anonymous_on_blocked_page_ends_on_login_without_the_page(self):
        self.client.logout()
        res = self.client.get(reverse("frontend:deposit"), follow=True)
        self.assertEqual(res.redirect_chain[-1][0], reverse("frontend:login") + "?next=/")

    def test_blocked_actions_are_refused_before_reaching_the_backend(self):
        with mock.patch("frontend.views.run_action") as run:
            for name, kwargs in HOME_ONLY_BLOCKED_ACTIONS:
                with self.subTest(action=name):
                    res = self.client.post(reverse(name, kwargs=kwargs),
                                           {"amount": "50", "cpf": "52998224725", "key_type": "cpf",
                                            "key": "52998224725", "current_password": "s3nha-forte",
                                            "new_password": "nova-s3nha-9", "new_password_confirmation": "nova-s3nha-9"},
                                           HTTP_X_IDEMPOTENCY_KEY="key-12345678")
                    self.assertEqual(res.status_code, 503)
                    self.assertEqual(res.json(), {"ok": False, "locked": True,
                                                  "message": "Esta área está temporariamente indisponível."})
        run.assert_not_called()
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("s3nha-forte"))  # troca de senha não passou

    def test_home_actions_keep_working(self):
        with mock.patch("frontend.views.run_action", return_value={"ok": False, "message": "regra"}) as run:
            for name, kwargs in HOME_ONLY_OPEN_ACTIONS:
                with self.subTest(action=name):
                    res = self.client.post(reverse(name, kwargs=kwargs), {"code": "ABC"},
                                           HTTP_X_IDEMPOTENCY_KEY="key-12345678")
                    self.assertNotEqual(res.status_code, 503)
                    self.assertNotIn("locked", res.json())
        self.assertTrue(run.called)

    def test_statement_is_locked_but_notifications_stay_open(self):
        res = self.client.get(reverse("frontend:statement"))
        self.assertEqual(res.status_code, 503)
        self.assertTrue(res.json()["locked"])
        self.assertEqual(self.client.get(reverse("frontend:notifications")).status_code, 200)

    def test_actions_still_require_login_first(self):
        self.client.logout()
        self.assertEqual(self.client.post(reverse("frontend:action_withdraw")).status_code, 401)

    @override_settings(FRONTEND_ONLY_HOME=False)
    def test_off_changes_nothing(self):
        html = self.client.get(reverse("frontend:home")).content.decode()
        self.assertNotIn("data-locked", html)
        self.assertNotIn("is-locked", html)
        self.assertNotIn("areaLockedModal", html)
        for name, kwargs in HOME_ONLY_BLOCKED_PAGES:
            with self.subTest(page=name):
                self.assertNotEqual(self.client.get(reverse(name, kwargs=kwargs)).status_code, 302)

    @override_settings()
    def test_off_when_setting_is_missing(self):
        from django.conf import settings
        del settings.FRONTEND_ONLY_HOME
        self.assertEqual(self.client.get(reverse("frontend:team")).status_code, 200)


# Saldo em recálculo: patrimônio e saldo para investir escondidos em todo lugar; saque segue normal.
def fake_wallet_distinct(user):
    from decimal import Decimal
    # Valores que não aparecem em nenhum outro lugar da página: se vazarem, o teste pega.
    return {"invest_balance": Decimal("777.30"), "withdraw_balance": Decimal("41.90")}


RECALC_LEAKS = ("777,30", "819,20", "77730", "81920")  # invest, total (brl) e em centavos


@override_settings(FRONTEND_BALANCE_RECALC=True, FRONTEND_ONLY_HOME=False,
                   FRONTEND_WALLET_PROVIDER="frontend.tests.fake_wallet_distinct")
class BalanceRecalcTests(TestCase):
    def setUp(self):
        CALLS.clear()
        self.user = get_user_model().objects.create_user(username="11987654321", password="s3nha-forte")
        self.client.force_login(self.user)

    def assert_no_leak(self, text):
        for value in RECALC_LEAKS:
            self.assertNotIn(value, text)

    def test_home_hides_total_and_invest_but_keeps_withdraw(self):
        for extra in ({}, SPA):
            with self.subTest(spa=bool(extra)):
                res = self.client.get(reverse("frontend:home"), **extra)
                html = res.json()["html"] if extra else res.content.decode()
                self.assertEqual(html.count("Recalculando saldo..."), 2)
                self.assertIn('data-wallet="withdraw_balance">R$ 41,90</p>', html)
                # Sem data-wallet nos dois: o home.js não troca a mensagem por número depois de uma ação.
                self.assertNotIn('data-wallet="total_balance"', html)
                self.assertNotIn('data-wallet="invest_balance"', html)
                self.assertNotIn("data-invest-cents", html)
                self.assert_no_leak(html)

    def test_profile_and_deposit_also_hide_invest(self):
        for name in ("frontend:profile", "frontend:deposit"):
            with self.subTest(page=name):
                html = self.client.get(reverse(name)).content.decode()
                self.assertIn("Recalculando saldo...", html)
                self.assertNotIn('data-wallet="invest_balance"', html)
                self.assert_no_leak(html)

    def test_activate_buttons_are_locked_with_their_own_notice(self):
        html = self.client.get(reverse("frontend:home")).content.decode()
        buttons = len(re.findall(r'class="home-product-btn', html))
        self.assertGreater(buttons, 0)
        self.assertEqual(html.count('data-locked="recalcLockedModal"'), buttons)
        self.assertContains(self.client.get(reverse("frontend:home")), 'id="recalcLockedModal" role="dialog"')
        self.assertIn("Ativação temporariamente indisponível", html)

    @override_settings(FRONTEND_PURCHASE_ACTION="frontend.tests.fake_purchase")
    def test_purchase_is_refused_on_the_server(self):
        res = self.client.post(reverse("frontend:action_purchase", kwargs={"product_id": "t1"}),
                               HTTP_X_IDEMPOTENCY_KEY="key-12345678")
        self.assertEqual(res.status_code, 503)
        self.assertEqual(res.json(), {"ok": False, "locked": True, "message":
                                      "A ativação de equipamentos está indisponível enquanto recalculamos os saldos."})
        self.assertEqual(CALLS, [])

    @override_settings(FRONTEND_CHECKIN_ACTION="frontend.tests.fake_ok_checkin")
    def test_action_response_only_updates_withdraw_balance(self):
        data = self.client.post(reverse("frontend:action_checkin")).json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["wallet"], {"withdraw_balance": "R$ 41,90"})
        self.assertNotIn("invest_balance_cents", data)
        self.assert_no_leak(str(data))

    @override_settings(FRONTEND_ONLY_HOME=True)
    def test_works_together_with_home_only_lock(self):
        html = self.client.get(reverse("frontend:home")).content.decode()
        self.assertIn('id="areaLockedModal"', html)
        self.assertIn('id="recalcLockedModal"', html)
        self.assertEqual(html.count("Recalculando saldo..."), 2)

    @override_settings(FRONTEND_BALANCE_RECALC=False)
    def test_off_shows_values_as_before(self):
        html = self.client.get(reverse("frontend:home")).content.decode()
        self.assertNotIn("Recalculando saldo", html)
        self.assertNotIn("recalcLockedModal", html)
        self.assertIn('data-wallet="total_balance">R$ 819,20</p>', html)
        self.assertIn('data-wallet="invest_balance">R$ 777,30</p>', html)
        self.assertIn('data-invest-cents="77730"', html)

    @override_settings()
    def test_off_when_setting_is_missing(self):
        from django.conf import settings
        del settings.FRONTEND_BALANCE_RECALC
        self.assertNotContains(self.client.get(reverse("frontend:home")), "Recalculando saldo")


# Saldo para saque de demonstração: contador no Início, sempre com o selo.
DEMO_SEAL = "Seu saldo está sendo calculado"


@override_settings(FRONTEND_DEMO_WITHDRAW_PROVIDER="preview.demo_withdraw.state", FRONTEND_BALANCE_RECALC=False,
                   FRONTEND_ONLY_HOME=False, FRONTEND_WALLET_PROVIDER="frontend.tests.fake_wallet_distinct")
class DemoWithdrawHomeTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="11987654321", password="s3nha-forte")
        self.client.force_login(self.user)

    def test_withdraw_starts_calculating_at_200_with_seal(self):
        for extra in ({}, SPA):
            with self.subTest(spa=bool(extra)):
                res = self.client.get(reverse("frontend:home"), **extra)
                html = res.json()["html"] if extra else res.content.decode()
                self.assertRegex(html, r'class="home-balance-value demo-ticker is-calculating" data-demo-withdraw '
                                       r'data-cents="20000"\s+data-rate-cents-per-hour="5000">')
                self.assertIn('<span class="demo-value">R$ 200,00</span>', html)
                self.assertIn("Calculando...", html)
                # Selo no saque e no patrimônio (que soma o saque de demonstração).
                self.assertEqual(html.count(DEMO_SEAL), 2)
                self.assertIn('<span class="demo-value">R$ 977,30</span>', html)  # 777,30 + 200,00
                # Sem data-wallet: as respostas das ações não sobrescrevem o contador.
                self.assertNotIn('data-wallet="withdraw_balance"', html)
                self.assertNotIn('data-wallet="total_balance"', html)
                self.assertNotIn("41,90", html)  # o saque do provider normal não aparece

    @override_settings(FRONTEND_BALANCE_RECALC=True)
    def test_with_recalc_total_keeps_the_message_and_withdraw_keeps_the_seal(self):
        html = self.client.get(reverse("frontend:home")).content.decode()
        self.assertEqual(html.count("Recalculando saldo..."), 2)
        self.assertIn("data-demo-withdraw", html)
        self.assertNotIn("data-demo-total", html)
        self.assertEqual(html.count(DEMO_SEAL), 1)

    @override_settings(FRONTEND_DEMO_WITHDRAW_PROVIDER=None)
    def test_off_shows_the_normal_withdraw_and_saves_nothing(self):
        from preview.models import DemoWithdrawBalance
        html = self.client.get(reverse("frontend:home")).content.decode()
        self.assertNotIn(DEMO_SEAL, html)
        self.assertNotIn("data-demo-withdraw", html)
        self.assertIn('data-wallet="withdraw_balance">R$ 41,90</p>', html)
        self.assertFalse(DemoWithdrawBalance.objects.exists())


# Regra do Caio (25/09): o admin vê exatamente o que o usuário vê — as travas temporárias valem para todos.
@override_settings(FRONTEND_ONLY_HOME=True, FRONTEND_BALANCE_RECALC=True,
                   FRONTEND_DEMO_WITHDRAW_PROVIDER="preview.demo_withdraw.state")
class AdminSeesWhatUsersSeeTests(TestCase):
    def test_staff_gets_the_same_locks_recalc_and_demo_as_a_common_user(self):
        admin = get_user_model().objects.create_user(username="admin-teste", password="x", is_staff=True,
                                                     is_superuser=True)
        self.client.force_login(admin)
        html = self.client.get(reverse("frontend:home")).content.decode()
        self.assertIn('id="areaLockedModal"', html)
        self.assertEqual(html.count("Recalculando saldo..."), 2)
        self.assertIn("data-demo-withdraw", html)
        self.assertIn(DEMO_SEAL, html)
        self.assertRedirects(self.client.get(reverse("frontend:team")), reverse("frontend:home"),
                             fetch_redirect_response=False)
        self.assertEqual(self.client.get(reverse("frontend:statement")).status_code, 503)
