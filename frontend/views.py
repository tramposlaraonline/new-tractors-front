import logging
import re
from urllib.parse import quote, urlencode
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.core.exceptions import ValidationError
from django.contrib.auth import authenticate, get_user_model, login, password_validation
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import LoginView as DjangoLoginView, RedirectURLMixin, redirect_to_login
from django.http import Http404, HttpResponseRedirect, JsonResponse
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.cache import patch_vary_headers
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.debug import sensitive_post_parameters
from django.views import View
from django.views.generic import TemplateView
from django.views.generic.edit import FormView

from .templatetags.frontend_format import brl
from .forms import PhoneLoginForm, RegisterForm, mobile_to_username, normalize_phone
from .channels import get_channels
from .qr import pix_qr_data_uri, safe_image_src
from .validators import PIX_KEY_TYPES, clean_cpf, clean_pix_key
from .providers import (
    get_checkin_state, get_demo_withdraw, get_header_state, get_products, get_profile_state, get_roulette_state, get_wallet_summary,
    get_deposit_charge, get_deposit_state, get_notifications, get_purchases, get_team,
    get_withdraw_history,
    get_withdraw_state, run_action,
)

# Header enviado pelo app.js ao trocar de aba: pede só o fragmento da tela, em JSON.
SPA_HEADER = "X-SPA-Request"

# Abas da navbar, na ordem em que aparecem.
APP_TABS = [
    {"key": "home", "label": "Início", "url_name": "frontend:home"},
    {"key": "team", "label": "Equipe", "url_name": "frontend:team"},
    {"key": "deposit", "label": "Depositar", "url_name": "frontend:deposit"},
    {"key": "purchases", "label": "Compras", "url_name": "frontend:purchases"},
    {"key": "profile", "label": "Perfil", "url_name": "frontend:profile"},
]

# Menu lateral do desktop: sem Depositar (vira o botão "Depositar Saldo") e com Extrato.
SIDEBAR_ITEMS = [
    {"key": "home", "label": "Início", "url_name": "frontend:home"},
    {"key": "team", "label": "Equipe", "url_name": "frontend:team"},
    {"key": "purchases", "label": "Compras", "url_name": "frontend:purchases"},
    {"key": "statement", "label": "Extrato", "url_name": "frontend:statement_page"},
    {"key": "profile", "label": "Perfil", "url_name": "frontend:profile"},
]


STATEMENT_FILTER_LABELS = [
    ("all", "Todos"), ("income", "Rendimentos & Bônus"), ("roulette", "Roleta"),
    ("deposit", "Depósitos"), ("withdraw", "Saques"),
]


def user_display(user):
    name = user.get_full_name().strip() or user.get_username()
    parts = name.split()
    initials = (parts[0][0] + (parts[-1][0] if len(parts) > 1 else "")).upper() if parts else "?"
    return {"user_name": name, "user_initials": initials}


def wants_json(request):
    return "application/json" in request.headers.get("Accept", "")


def json_form_errors(form):
    errors = {field: list(msgs) for field, msgs in form.errors.items() if field != "__all__"}
    message = " ".join(form.non_field_errors()) or None
    return JsonResponse({"ok": False, "message": message, "errors": errors}, status=400)


def channel_context():
    ch = get_channels()
    return {"support_url": ch["support_url"], "whatsapp_url": ch["support_whatsapp"],
            "telegram_url": ch["support_telegram"], "community": ch}


# Trava temporária de login e cadastro. Ligada por padrão: para liberar, FRONTEND_AUTH_LOCKED = False.
AUTH_LOCK_NOTICES = {
    "login": {
        "title": "Login temporariamente indisponível",
        "message": "O acesso à plataforma está indisponível no momento. O prazo de normalização é até 22h de hoje. "
                   "Entre nos nossos canais de comunicação oficiais clicando nos botões abaixo, e receba o aviso "
                   "assim que os acessos forem normalizados.",
    },
    "register": {
        "title": "Cadastro temporariamente indisponível",
        "message": "O cadastro na plataforma está indisponível no momento. O prazo de normalização é até 22h de hoje. "
                   "Entre nos nossos canais de comunicação oficiais clicando nos botões abaixo, e receba o aviso "
                   "assim que os cadastros forem normalizados.",
    },
}


def auth_locked():
    return getattr(settings, "FRONTEND_AUTH_LOCKED", True)


def home_only():
    """Bloqueio temporário (FRONTEND_ONLY_HOME): só o que é marcado com `open_when_home_only` responde."""
    return getattr(settings, "FRONTEND_ONLY_HOME", False)


# Aviso ao tocar numa aba/botão bloqueado (modal) e resposta das ações bloqueadas (JSON 503).
AREA_LOCK_NOTICE = {
    "title": "Área temporariamente indisponível",
    "message": "Esta área da plataforma está indisponível no momento. Acompanhe nossos canais de comunicação "
               "oficiais para saber quando ela for liberada.",
}
AREA_LOCKED_MESSAGE = "Esta área está temporariamente indisponível."
HOME_ONLY_OPEN_TABS = {"home"}


def balance_recalc():
    """Saldo em recálculo (FRONTEND_BALANCE_RECALC): esconde patrimônio e saldo para investir, trava a ativação."""
    return getattr(settings, "FRONTEND_BALANCE_RECALC", False)


RECALC_LOCK_NOTICE = {
    "title": "Ativação temporariamente indisponível",
    "message": "Estamos recalculando os saldos para investir. A ativação de equipamentos volta assim que o "
               "recálculo terminar.",
}
RECALC_LOCKED_MESSAGE = "A ativação de equipamentos está indisponível enquanto recalculamos os saldos."


def nav_items(items):
    """Itens da navbar/menu lateral com `locked` marcado nas abas fechadas pelo bloqueio."""
    locked = home_only()
    return [{**item, "locked": locked and item["key"] not in HOME_ONLY_OPEN_TABS} for item in items]


def login_autocreate_enabled():
    # Ligado em preview/settings.py pela env FRONTEND_LOGIN_AUTOCREATE=1 (local ou Render).
    return getattr(settings, "FRONTEND_LOGIN_AUTOCREATE", False)


class AuthLockMixin:
    """Com a trava ligada, recusa o POST antes de validar, autenticar ou criar usuário.

    Roda depois do CSRF (os decorators ficam no dispatch). A página continua abrindo normalmente;
    o aviso só aparece quando o usuário tenta entrar/cadastrar. JSON: 503 {"ok": false, "locked": true, ...}.
    """

    def lock_notice(self):
        return AUTH_LOCK_NOTICES[self.extra_context["auth_tab"]]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if auth_locked():
            context["auth_lock"] = self.lock_notice()
        return context

    def post(self, request, *args, **kwargs):
        if not auth_locked():
            return super().post(request, *args, **kwargs)
        notice = self.lock_notice()
        if wants_json(request):
            return JsonResponse({"ok": False, "locked": True, **notice}, status=503)
        # Form sem dados: um form preenchido rodaria a validação (e o authenticate do login) ao ser renderizado.
        form_kwargs = self.get_form_kwargs()
        form_kwargs.pop("data", None)
        form_kwargs.pop("files", None)
        context = self.get_context_data(form=self.get_form_class()(**form_kwargs), auth_lock_shown=True)
        return self.render_to_response(context, status=503)


class LoginView(AuthLockMixin, DjangoLoginView):
    """Login por celular + senha.

    Herda do LoginView do Django (CSRF, `next` seguro, never_cache, sensitive_post_parameters).
    Com `Accept: application/json` responde JSON para o auth.js abrir o modal de sucesso;
    sem JS, cai no fluxo padrão de POST + redirect.
    """

    template_name = "frontend/auth/login.html"
    form_class = PhoneLoginForm
    redirect_authenticated_user = True
    extra_context = {"auth_tab": "login"}

    def get_context_data(self, **kwargs):
        return {**super().get_context_data(**kwargs), "community": get_channels()}

    def form_valid(self, form):
        response = super().form_valid(form)
        if wants_json(self.request):
            return JsonResponse({"ok": True, "redirect": self.get_success_url()})
        return response

    def form_invalid(self, form):
        if login_autocreate_enabled():
            response = self._autocreate_login(form)
            if response is not None:
                return response
        if wants_json(self.request):
            return json_form_errors(form)
        return super().form_invalid(form)

    def _autocreate_login(self, form):
        """Telefone sem conta -> cria com a senha digitada e loga.

        Conta que já existe continua exigindo a senha correta (não cria nem entra sem checar).
        Ligado por preview/settings.py (env FRONTEND_LOGIN_AUTOCREATE=1).
        """
        mobile = form.cleaned_data.get("mobile") or normalize_phone(form.data.get("mobile", ""))
        password = form.data.get("password", "") or ""
        if not (8 <= len(mobile) <= 11) or len(password) < 6:
            return None  # telefone/senha inválidos: deixa a validação normal responder
        User = get_user_model()
        username = mobile_to_username(mobile)
        if User.objects.filter(username=username).exists():
            return None  # já existe: senha certa loga, errada dá o erro genérico normal
        user = User.objects.create_user(username=username, password=password)
        login(self.request, user, backend=settings.AUTHENTICATION_BACKENDS[0])
        if wants_json(self.request):
            return JsonResponse({"ok": True, "redirect": self.get_success_url()})
        return HttpResponseRedirect(self.get_success_url())


@method_decorator([sensitive_post_parameters("password", "password_confirmation"), csrf_protect, never_cache],
                  name="dispatch")
class RegisterView(AuthLockMixin, RedirectURLMixin, FormView):
    """Cadastro: cria o usuário e já faz o login, como pedido (o original mandava para /login).

    Mesmo contrato do LoginView: JSON para o auth.js (modal "Acesso Autorizado!" + redirect),
    POST + redirect sem JS. `next` só é aceito se for do mesmo domínio.
    """

    template_name = "frontend/auth/register.html"
    form_class = RegisterForm
    extra_context = {"auth_tab": "register"}
    next_page = settings.LOGIN_REDIRECT_URL

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return HttpResponseRedirect(self.get_success_url())
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context[self.redirect_field_name] = self.get_redirect_url()
        context["community"] = get_channels()
        return context

    def form_valid(self, form):
        user = form.save()
        if user is None:
            return self.form_invalid(form)
        # authenticate() passa pelos backends do projeto e marca user.backend para o login().
        authed = authenticate(self.request, username=mobile_to_username(form.cleaned_data["phone"]),
                              password=form.cleaned_data["password"])
        backend = getattr(authed, "backend", None) or settings.AUTHENTICATION_BACKENDS[0]
        login(self.request, authed or user, backend=backend)
        if wants_json(self.request):
            return JsonResponse({"ok": True, "redirect": self.get_success_url()})
        return HttpResponseRedirect(self.get_success_url())

    def form_invalid(self, form):
        if wants_json(self.request):
            return json_form_errors(form)
        return super().form_invalid(form)


def is_spa_request(request):
    return request.headers.get(SPA_HEADER) == "1"


@method_decorator(never_cache, name="dispatch")
class AppPageView(LoginRequiredMixin, TemplateView):
    """Tela da área logada.

    Acesso direto (primeira carga, F5, link colado): devolve a casca completa (navbar + Chat + tela).
    Troca de aba pelo app.js (header X-SPA-Request: 1): devolve só o fragmento da tela em JSON,
    `{"tab", "title", "html"}`, e a casca continua na página sem reload.
    """

    tab = None
    title = None
    page_template = None
    template_name = "frontend/app/shell.html"
    # Bloqueio temporário (FRONTEND_ONLY_HOME): fechada por padrão; só a tela que liga isto continua abrindo.
    open_when_home_only = False

    def dispatch(self, request, *args, **kwargs):
        if home_only() and not self.open_when_home_only:
            # Link direto, F5 ou navegação SPA: volta para o Início (o app.js segue o redirect com carga completa).
            return HttpResponseRedirect(reverse("frontend:home"))
        return super().dispatch(request, *args, **kwargs)

    def handle_no_permission(self):
        # Sessão expirada no meio da navegação SPA: o JS faz a ida ao login com carga completa.
        if is_spa_request(self.request):
            login_redirect = redirect_to_login(self.request.get_full_path())
            return JsonResponse({"ok": False, "redirect": login_redirect.url}, status=401)
        return super().handle_no_permission()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            "app_tab": self.tab,
            "app_tabs": nav_items(APP_TABS),
            "sidebar_items": nav_items(SIDEBAR_ITEMS),
            "page_title": self.title,
            "page_template": self.page_template,
            "statement_filters": STATEMENT_FILTER_LABELS,
            "home_only": home_only(),
            "balance_recalc": balance_recalc(),
            **channel_context(),
        })
        if context["home_only"]:
            context["area_lock"] = AREA_LOCK_NOTICE
        if context["balance_recalc"]:
            context["recalc_lock"] = RECALC_LOCK_NOTICE
        if not is_spa_request(self.request):
            # Cabeçalho e modais de boas-vindas só existem na casca; numa troca de aba já estão na página.
            context["header"] = {**user_display(self.request.user), **get_header_state(self.request.user)}

        return context

    def render_to_response(self, context, **response_kwargs):
        if is_spa_request(self.request):
            html = render_to_string(self.page_template, context, request=self.request)
            response = JsonResponse({"ok": True, "tab": self.tab, "title": f"{self.title} • New Tractors", "html": html})
        else:
            response = super().render_to_response(context, **response_kwargs)
        # A mesma URL tem duas representações (casca inteira x fragmento JSON): nunca misturar em cache.
        patch_vary_headers(response, (SPA_HEADER,))
        return response

class HomeView(AppPageView):
    """Aba Início: card "Meu Patrimônio" com os saldos do usuário."""

    open_when_home_only = True

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["wallet"] = get_wallet_summary(self.request.user)
        demo = get_demo_withdraw(self.request.user)
        if demo:
            # Contador do home.js: parte do valor atual e sobe no ritmo informado (sempre com o selo de demonstração).
            context["demo_withdraw"] = {"balance": demo["balance"], "cents": _cents(demo["balance"]),
                                        "rate_cents_per_hour": _cents(demo["rate_per_hour"]),
                                        "total": context["wallet"]["invest_balance"] + demo["balance"]}
        context["checkin"] = get_checkin_state(self.request.user)
        context["products"] = get_products(self.request.user)
        context["roulette"] = get_roulette_state(self.request.user)
        return context

def _icon(paths):
    return ('<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" '
            f'stroke-linejoin="round">{paths}</svg>')


# Itens do menu "Financeiro" do Perfil (textos iguais ao site). `route`/`spa_tab` só onde a tela já existe.
PROFILE_MENU = [
    {"key": "deposit", "title": "Fazer depósito", "subtitle": "Adicionar saldo para ativar novos equipamentos",
     "tone": "green", "route": "frontend:deposit", "spa_tab": "deposit",
     "icon": _icon('<circle cx="12" cy="12" r="10"/><path d="M12 8v8"/><path d="m8 12 4 4 4-4"/>')},
    {"key": "withdraw", "title": "Realizar saque", "subtitle": "Transferência instantânea para sua chave PIX",
     "tone": "gold", "route": "frontend:withdraw", "spa_tab": "profile", "icon": _icon('<rect width="20" height="14" x="2" y="5" rx="2"/><path d="M2 10h20"/>')},
    {"key": "pix", "title": "Conta Pix", "subtitle": "Chave cadastrada para recebimento de saques", "tone": "gray",
     "route": "frontend:withdraw", "spa_tab": "profile",
     "icon": _icon('<rect width="7" height="7" x="3" y="3" rx="1"/><rect width="7" height="7" x="14" y="3" rx="1"/>'
                   '<rect width="7" height="7" x="14" y="14" rx="1"/><rect width="7" height="7" x="3" y="14" rx="1"/>')},
    {"key": "password", "title": "Alterar senha", "subtitle": "Atualize sua senha de acesso", "tone": "gray",
     "modal": "passwordModal",
     "icon": _icon('<rect width="18" height="11" x="3" y="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>')},
    {"key": "activity", "title": "Histórico de atividades", "subtitle": "Depósitos, rendimentos diários e bônus",
     "tone": "gray", "route": "frontend:statement_page", "spa_tab": "statement",
     "icon": _icon('<path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"/><path d="M14 2v4a2 2 0 0 0 2 2h4"/>'
                   '<path d="M10 9H8"/><path d="M16 13H8"/><path d="M16 17H8"/>')},
    {"key": "investments", "title": "Meus investimentos", "subtitle": "Acompanhar equipamentos e rendimentos em tempo real",
     "tone": "green", "route": "frontend:purchases", "spa_tab": "purchases",
     "icon": _icon('<path d="m12.83 2.18a2 2 0 0 0-1.66 0L2.6 6.08a1 1 0 0 0 0 1.83l8.58 3.91a2 2 0 0 0 1.66 0l8.58-3.9'
                   'a1 1 0 0 0 0-1.83Z"/><path d="m22 17.65-9.17 4.16a2 2 0 0 1-1.66 0L2 17.65"/>'
                   '<path d="m22 12.65-9.17 4.16a2 2 0 0 1-1.66 0L2 12.65"/>')},
    {"key": "withdraw_history", "title": "Histórico de saques", "subtitle": "Comprovantes de liquidação PIX", "tone": "gold",
     "route": "frontend:withdraw_history", "spa_tab": "profile",
     "icon": _icon('<path d="M22 12h-2.48a2 2 0 0 0-1.93 1.46l-2.35 8.36a.25.25 0 0 1-.48 0L9.24 2.18a.25.25 0 0 0-.48 0'
                   'l-2.35 8.36A2 2 0 0 1 4.49 12H2"/>')},
    {"key": "support", "title": "Suporte oficial", "subtitle": "Atendimento no WhatsApp e Telegram", "tone": "gray",
     "modal": "supportModal",
     "icon": _icon('<path d="M3 14h3a2 2 0 0 1 2 2v3a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2v-7a9 9 0 0 1 18 0v7a2 2 0 0 1-2 2h-1'
                   'a2 2 0 0 1-2-2v-3a2 2 0 0 1 2-2h3"/>')},
    {"key": "about", "title": "Sobre a New Tractors", "subtitle": "Missão, termos regulatórios e sustentabilidade",
     "modal": "aboutModal",
     "tone": "gray", "icon": _icon('<circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/>')},
]


def profile_menu():
    items = []
    for item in PROFILE_MENU:
        entry = {**item, "href": "", "external": False}
        if item.get("route"):
            entry["href"] = reverse(item["route"])
        items.append(entry)
    return items

class ProfileView(AppPageView):
    """Aba Perfil (/my): dados da conta, carteira e menu."""

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        context.update({
            "wallet": get_wallet_summary(user),
            "profile": {**user_display(user), "phone": user.get_username(), **get_profile_state(user)},
            "profile_menu": profile_menu(),
        })
        return context


def _cents(value):
    return int((Decimal(value) * 100).to_integral_value())


class WithdrawView(AppPageView):
    """Solicitar Saque Pix (/withdraw). Sub-tela do Perfil: a aba ativa continua sendo Perfil."""

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        wallet = get_wallet_summary(self.request.user)
        state = get_withdraw_state(self.request.user)
        context.update({
            "wallet": wallet,
            "withdraw": state,
            "withdraw_js": {"balance_cents": _cents(wallet["withdraw_balance"]), "min_cents": _cents(state["min_amount"]),
                            "fee_bp": int(state["fee_percent"] * 100)},
        })
        return context

# =========================================================================
# AÇÕES DO INÍCIO (POST + JSON, chamadas pelo home.js)
# =========================================================================
logger = logging.getLogger(__name__)
GENERIC_ACTION_ERROR = "Não foi possível concluir agora. Tente novamente em instantes."


def _money(value):
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")


def _balances(user):
    """Estado atualizado que o front aplica na tela depois de cada ação."""
    wallet = get_wallet_summary(user)
    recalc = balance_recalc()  # patrimônio e saldo para investir ficam em "Recalculando saldo..." na tela
    shown = ("withdraw_balance",) if recalc else ("total_balance", "invest_balance", "withdraw_balance")
    payload = {
        "wallet": {key: brl(wallet[key]) for key in shown},
        "spins_available": get_roulette_state(user)["spins_available"],
    }
    if not recalc:
        payload["invest_balance_cents"] = _cents(wallet["invest_balance"])
    return payload


@method_decorator(never_cache, name="dispatch")
class HomeActionView(LoginRequiredMixin, View):
    """Base: login obrigatório (401 JSON), só POST com CSRF (middleware), erros sem stack trace."""

    http_method_names = ["post"]
    # Bloqueio temporário (FRONTEND_ONLY_HOME): fechada por padrão; só as ações do Início ligam isto.
    open_when_home_only = False

    def handle_no_permission(self):
        return JsonResponse({"ok": False, "message": "Sua sessão expirou. Entre novamente."}, status=401)

    def post(self, request, *args, **kwargs):
        if home_only() and not self.open_when_home_only:
            return JsonResponse({"ok": False, "locked": True, "message": AREA_LOCKED_MESSAGE}, status=503)
        try:
            status, payload = self.perform(request, *args, **kwargs)
        except Exception:  # noqa: BLE001 — registra e responde genérico; nunca vaza detalhe interno
            logger.exception("Falha na ação %s", type(self).__name__)
            return JsonResponse({"ok": False, "message": GENERIC_ACTION_ERROR}, status=500)
        if payload.get("ok"):
            payload.update(_balances(request.user))
        else:
            payload.setdefault("message", GENERIC_ACTION_ERROR)
        if not payload.get("ok") and status == 200:
            status = 400  # a regra de negócio recusou (saldo, código inválido, sem giros...)
        return JsonResponse(payload, status=status)

    def perform(self, request, *args, **kwargs):
        raise NotImplementedError


class CheckinActionView(HomeActionView):
    open_when_home_only = True

    def perform(self, request):
        result = run_action("FRONTEND_CHECKIN_ACTION", request.user)
        if not result.get("ok"):
            return 200, {"ok": False, "message": result.get("message")}
        payload = {"ok": True}
        if result.get("amount") is not None:
            payload["amount"] = brl(_money(result["amount"]))  # abre o modal "Check-in realizado!"
        return 200, payload


class BonusActionView(HomeActionView):
    open_when_home_only = True

    def perform(self, request):
        code = re.sub(r"\s+", "", request.POST.get("code", "")).upper()
        if not code:
            return 400, {"ok": False, "message": "Informe o código."}
        if len(code) > 32 or not re.fullmatch(r"[A-Z0-9_-]+", code):
            return 400, {"ok": False, "message": "Código inválido."}
        result = run_action("FRONTEND_BONUS_ACTION", request.user, code=code)
        if not result.get("ok"):
            return 200, {"ok": False, "message": result.get("message")}
        return 200, {"ok": True, "amount": brl(_money(result.get("amount")))}


class RouletteActionView(HomeActionView):
    open_when_home_only = True
    SEGMENTS = 7

    def perform(self, request):
        if get_roulette_state(request.user)["spins_available"] < 1:
            return 400, {"ok": False, "message": "Você não tem giros disponíveis."}
        result = run_action("FRONTEND_ROULETTE_ACTION", request.user)
        if not result.get("ok"):
            return 200, {"ok": False, "message": result.get("message")}
        segment = int(result.get("segment_index", 0)) % self.SEGMENTS
        return 200, {"ok": True, "prize_amount": brl(_money(result.get("prize_amount"))), "segment_index": segment}


class PurchaseActionView(HomeActionView):
    open_when_home_only = True

    def perform(self, request, product_id):
        if balance_recalc():  # ninguém compra com um saldo que não consegue ver
            return 503, {"ok": False, "locked": True, "message": RECALC_LOCKED_MESSAGE}
        if product_id not in {p["id"] for p in get_products(request.user)}:
            return 404, {"ok": False, "message": "Equipamento não encontrado."}
        key = request.headers.get("X-Idempotency-Key", "")
        if not re.fullmatch(r"[A-Za-z0-9-]{8,64}", key):
            return 400, {"ok": False, "message": GENERIC_ACTION_ERROR}
        result = run_action("FRONTEND_PURCHASE_ACTION", request.user, product_id=product_id, idempotency_key=key)
        if not result.get("ok"):
            return 200, {"ok": False, "message": result.get("message")}
        return 200, {"ok": True, "spins_awarded": int(result.get("spins_awarded") or 0)}


AMOUNT_RE = re.compile(r"\d{1,9}(\.\d{1,2})?")
WITHDRAW_OK_MESSAGE = "Saque enviado com sucesso! Estamos aguardando a confirmação da transferência."


def parse_amount(raw):
    """"45", "45.5", "45,50" e "1.234,56" -> Decimal. Qualquer outra coisa (negativo, 3 casas, texto) -> None."""
    text = (raw or "").strip().replace("R$", "").replace(" ", "")
    if "," in text:
        text = text.replace(".", "").replace(",", ".")
    if not AMOUNT_RE.fullmatch(text):
        return None
    return Decimal(text)


class WithdrawActionView(HomeActionView):
    """Validação no servidor antes de chamar o backend (o backend revalida de forma atômica)."""

    def perform(self, request):
        user = request.user
        state = get_withdraw_state(user)
        if not state["pix_key"]:
            return 400, {"ok": False, "message": "Cadastre sua chave Pix antes de solicitar saques."}
        amount = parse_amount(request.POST.get("amount"))
        if amount is None or amount <= 0:
            return 400, {"ok": False, "message": "Informe um valor válido para o saque."}
        if amount < state["min_amount"]:
            return 400, {"ok": False, "message": f"O valor mínimo para saque é {brl(state['min_amount'])}."}
        if amount > get_wallet_summary(user)["withdraw_balance"]:
            return 400, {"ok": False, "message": "Saldo insuficiente para este saque."}
        key = request.headers.get("X-Idempotency-Key", "")
        if not re.fullmatch(r"[A-Za-z0-9-]{8,64}", key):
            return 400, {"ok": False, "message": GENERIC_ACTION_ERROR}
        result = run_action("FRONTEND_WITHDRAW_ACTION", user, amount=amount, idempotency_key=key)
        if not result.get("ok"):
            return 200, {"ok": False, "message": result.get("message")}
        wallet = get_wallet_summary(user)
        html = render_to_string("frontend/app/pages/_withdraw_recent.html", {"withdraw": get_withdraw_state(user)},
                                request=request)
        return 200, {"ok": True, "message": result.get("message") or WITHDRAW_OK_MESSAGE,
                     "withdraw_balance_cents": _cents(wallet["withdraw_balance"]), "recent_html": html}


# =========================================================================
# DEPÓSITO PIX
# =========================================================================
CHARGE_ID_RE = re.compile(r"[A-Za-z0-9_-]{6,64}")


class DepositView(AppPageView):
    """Depositar Saldo Pix (/recharge)."""

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        state = get_deposit_state(self.request.user)
        context.update({
            "wallet": get_wallet_summary(self.request.user),
            "deposit": state,
            "deposit_js": {"min_cents": _cents(state["min_amount"]), "max_cents": _cents(state["max_amount"])},
        })
        return context


class DepositPaymentView(AppPageView):
    """Pagamento da cobrança (/recharge/<id>): QR Code, copia e cola, contagem e confirmação."""

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        charge_id = kwargs["charge_id"]
        charge = get_deposit_charge(self.request.user, charge_id) if CHARGE_ID_RE.fullmatch(charge_id) else None
        if not charge:
            raise Http404("Cobrança não encontrada.")
        code = str(charge.get("pix_code") or "")
        expires = charge.get("expires_at")
        context["charge"] = {
            "id": charge_id, "amount": Decimal(charge["amount"]), "pix_code": code,
            "qr_src": safe_image_src(charge.get("qr_image")) or pix_qr_data_uri(code),
            "expires_iso": expires.isoformat() if expires else "", "status": charge.get("status") or "pending",
        }
        return context


class CpfActionView(HomeActionView):
    def perform(self, request):
        cpf, error = clean_cpf(request.POST.get("cpf"))
        if error:
            return 400, {"ok": False, "message": error, "errors": {"cpf": error}}
        result = run_action("FRONTEND_CPF_ACTION", request.user, cpf=cpf)
        if not result.get("ok"):
            return 200, {"ok": False, "message": result.get("message")}
        return 200, {"ok": True}


class DepositActionView(HomeActionView):
    def perform(self, request):
        state = get_deposit_state(request.user)
        if not state["cpf_registered"]:
            return 400, {"ok": False, "message": "Cadastre o CPF do titular antes de depositar.", "need_cpf": True}
        amount = parse_amount(request.POST.get("amount"))
        if amount is None or amount <= 0:
            return 400, {"ok": False, "message": "Informe um valor válido para o depósito."}
        if amount < state["min_amount"]:
            return 400, {"ok": False, "message": f"O valor mínimo para depósito é {brl(state['min_amount'])}."}
        if amount > state["max_amount"]:
            return 400, {"ok": False, "message": f"O valor máximo por depósito é {brl(state['max_amount'])}."}
        key = request.headers.get("X-Idempotency-Key", "")
        if not re.fullmatch(r"[A-Za-z0-9-]{8,64}", key):
            return 400, {"ok": False, "message": GENERIC_ACTION_ERROR}
        result = run_action("FRONTEND_DEPOSIT_ACTION", request.user, amount=amount, idempotency_key=key)
        if not result.get("ok"):
            return 200, {"ok": False, "message": result.get("message")}
        charge_id = str(result.get("charge_id") or "")
        if not CHARGE_ID_RE.fullmatch(charge_id):
            raise ValueError("charge_id inválido devolvido pelo backend")
        return 200, {"ok": True, "redirect": reverse("frontend:deposit_payment", args=[charge_id])}


class DepositStatusView(HomeActionView):
    """Consultado a cada 5s pela tela de pagamento e pelo botão "Já fiz o Pix" (manual=1)."""

    def perform(self, request, charge_id):
        if not CHARGE_ID_RE.fullmatch(charge_id):
            return 404, {"ok": False, "message": "Cobrança não encontrada."}
        result = run_action("FRONTEND_DEPOSIT_STATUS", request.user, charge_id=charge_id,
                            manual_check=request.POST.get("manual") == "1")
        if not result.get("ok"):
            return 200, {"ok": False, "message": result.get("message")}
        status = result.get("status") if result.get("status") in ("pending", "paid", "expired") else "pending"
        payload = {"ok": True, "status": status}
        if status == "paid":
            payload["redirect"] = reverse("frontend:profile")
        return 200, payload


class PixKeyActionView(HomeActionView):
    def perform(self, request):
        key_type = request.POST.get("key_type", "")
        if key_type not in PIX_KEY_TYPES:
            key, error = None, "Selecione o tipo de chave."
        else:
            key, error = clean_pix_key(key_type, request.POST.get("key"))
        if error:
            return 400, {"ok": False, "message": error, "errors": {"key": error}}
        # Titular e documento vêm do cadastro (o backend confere se a chave é do próprio titular).
        result = run_action("FRONTEND_PIX_KEY_ACTION", request.user, key_type=key_type, key=key)
        if not result.get("ok"):
            return 200, {"ok": False, "message": result.get("message")}
        return 200, {"ok": True}


# =========================================================================
# MINHAS COMPRAS
# =========================================================================
def countdown_label(target, now=None):
    """Tempo até o próximo crédito no formato do site: "22h 04min" (nunca negativo)."""
    if not target:
        return "—"
    from django.utils import timezone
    seconds = max(0, int((target - (now or timezone.now())).total_seconds()))
    return f"{seconds // 3600}h {seconds % 3600 // 60:02d}min"


class PurchasesView(AppPageView):
    """Minhas Compras (/record): resumo e contratos ativos."""

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        data = get_purchases(self.request.user)
        for contract in data["contracts"]:
            nxt = contract.get("next_credit_at")
            contract["next_credit_label"] = countdown_label(nxt) if contract["is_active"] else "Finalizado"
            contract["next_credit_iso"] = nxt.isoformat() if nxt and contract["is_active"] else ""
        context["purchases"] = data
        return context


# =========================================================================
# EXTRATO (modal global, carregado sob demanda)
# =========================================================================
from .statement import FILTER_KINDS, FILTERS, get_statement, get_statement_summary  # noqa: E402


@method_decorator(never_cache, name="dispatch")
class StatementView(LoginRequiredMixin, View):
    """GET /acoes/extrato?filtro=<all|income|roulette|deposit|withdraw>&offset=N -> {ok, html, has_more, next_offset}."""

    http_method_names = ["get"]
    PAGE_SIZE = 20
    MAX_OFFSET = 5000

    def handle_no_permission(self):
        return JsonResponse({"ok": False, "message": "Sua sessão expirou. Entre novamente."}, status=401)

    def get(self, request):
        if home_only():  # o Extrato fica fechado no bloqueio (modal do Início e página /extrato)
            return JsonResponse({"ok": False, "locked": True, "message": AREA_LOCKED_MESSAGE}, status=503)
        filter_key = request.GET.get("filtro", "all")
        if filter_key not in FILTER_KINDS:
            filter_key = "all"
        try:
            offset = min(max(0, int(request.GET.get("offset", 0))), self.MAX_OFFSET)
        except (TypeError, ValueError):
            offset = 0
        try:
            items = get_statement(request.user, filter_key, offset, self.PAGE_SIZE + 1)
        except Exception:  # noqa: BLE001
            logger.exception("Falha ao carregar extrato")
            return JsonResponse({"ok": False, "message": "Não foi possível carregar o extrato agora."}, status=500)
        has_more = len(items) > self.PAGE_SIZE
        items = items[:self.PAGE_SIZE]
        template = ("frontend/app/pages/_statement_page_items.html" if request.GET.get("layout") == "page"
                    else "frontend/app/pages/_statement_items.html")
        html = render_to_string(template,
                                {"items": items, "first_page": offset == 0}, request=request)
        return JsonResponse({"ok": True, "html": html, "has_more": has_more, "next_offset": offset + len(items)})


# =========================================================================
# EQUIPE
# =========================================================================


class TeamView(AppPageView):
    """Minha Equipe & Indicações (/equipe): resumo, convite, níveis, membros e metas."""

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        team = get_team(self.request.user)
        invite_url = ""
        if team["invite_code"]:
            invite_url = self.request.build_absolute_uri(reverse("frontend:register")) + "?" + urlencode(
                {"code": team["invite_code"]})
        message = f"Venha fazer parte da New Tractors! Cadastre-se pelo meu link: {invite_url}"
        context.update({
            "team": team,
            "invite_url": invite_url,
            "whatsapp_share_url": "https://wa.me/?text=" + quote(message) if invite_url else "",
            "team_section": "goals" if self.request.GET.get("aba") == "metas" else "team",
        })
        return context


class StatementPageView(AppPageView):
    """Extrato consolidado (/extrato): totais + lista paginada (mesmo endpoint do modal, layout=page)."""

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        summary = get_statement_summary(self.request.user)
        context["statement"] = {
            **summary,
            "filters": [(key, label, summary["counts"][key]) for key, label in STATEMENT_FILTER_LABELS],
        }
        return context


class WithdrawHistoryView(AppPageView):
    """Histórico de Saques (/withdraw/history): sub-tela do Perfil."""

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["history"] = get_withdraw_history(self.request.user)
        return context


# =========================================================================
# NOTIFICAÇÕES
# =========================================================================
@method_decorator(never_cache, name="dispatch")
class NotificationsView(LoginRequiredMixin, View):
    """GET /acoes/notificacoes -> {ok, html, unread}. Carregado ao abrir o sino (sempre atualizado)."""

    http_method_names = ["get"]
    LIMIT = 50

    def handle_no_permission(self):
        return JsonResponse({"ok": False, "message": "Sua sessão expirou. Entre novamente."}, status=401)

    def get(self, request):
        try:
            items = get_notifications(request.user, 0, self.LIMIT)
        except Exception:  # noqa: BLE001
            logger.exception("Falha ao carregar notificações")
            return JsonResponse({"ok": False, "message": "Não foi possível carregar as notificações."}, status=500)
        html = render_to_string("frontend/app/pages/_notifications.html", {"items": items}, request=request)
        return JsonResponse({"ok": True, "html": html, "unread": sum(1 for i in items if not i.get("read"))})


class NotificationsReadView(HomeActionView):
    open_when_home_only = True  # o sino continua liberado no bloqueio

    def perform(self, request):
        result = run_action("FRONTEND_NOTIFICATIONS_READ_ACTION", request.user)
        return 200, {"ok": bool(result.get("ok")), **({"message": result["message"]} if result.get("message") else {})}


# =========================================================================
# PERFIL: ALTERAR SENHA / INÍCIO: PROCESSO SELETIVO
# =========================================================================
from django.contrib.auth import update_session_auth_hash  # noqa: E402


@method_decorator(sensitive_post_parameters("current_password", "new_password", "new_password_confirmation"),
                  name="dispatch")
class PasswordChangeActionView(HomeActionView):
    """Troca a senha do usuário logado (auth do Django) e mantém a sessão atual válida."""

    def perform(self, request):
        user = request.user
        current = request.POST.get("current_password", "")
        new = request.POST.get("new_password", "")
        confirmation = request.POST.get("new_password_confirmation", "")
        errors = {}
        if not current:
            errors["current_password"] = "Informe sua senha atual."
        elif not user.check_password(current):
            errors["current_password"] = "Senha atual incorreta."
        if len(new) < 6:
            errors["new_password"] = "A nova senha deve ter no mínimo 6 caracteres."
        elif len(new) > 128:
            errors["new_password"] = "A nova senha é muito longa."
        elif new == current:
            errors["new_password"] = "A nova senha deve ser diferente da atual."
        else:
            try:
                password_validation.validate_password(new, user)
            except ValidationError as exc:
                errors["new_password"] = " ".join(exc.messages)
        if "new_password" not in errors and new != confirmation:
            errors["new_password_confirmation"] = "As senhas não coincidem."
        if errors:
            return 400, {"ok": False, "message": next(iter(errors.values())), "errors": errors}
        user.set_password(new)
        user.save(update_fields=["password"])
        update_session_auth_hash(request, user)  # não derruba o login atual
        return 200, {"ok": True}


class RecruitActionView(HomeActionView):
    open_when_home_only = True
    MAX_LENGTH = 500

    def perform(self, request):
        message = (request.POST.get("message") or "").strip()
        if len(message) > self.MAX_LENGTH:
            error = f"Use no máximo {self.MAX_LENGTH} caracteres."
            return 400, {"ok": False, "message": error, "errors": {"message": error}}
        result = run_action("FRONTEND_RECRUIT_ACTION", request.user, message=message)
        if not result.get("ok"):
            return 200, {"ok": False, "message": result.get("message")}
        return 200, {"ok": True}
