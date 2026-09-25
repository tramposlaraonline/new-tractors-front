from django.contrib.auth.views import LogoutView
from django.urls import path
from django.views.generic import TemplateView

from . import views

app_name = "frontend"


def app_page(tab, title, view=views.AppPageView):
    return view.as_view(tab=tab, title=title, page_template=f"frontend/app/pages/{tab}.html")


# Paths iguais aos do site original (/login, /reg, /forgot_password).
urlpatterns = [
    path("login", views.LoginView.as_view(), name="login"),
    path("reg", views.RegisterView.as_view(), name="register"),
    # Placeholder até chegar o print dessa tela.
    path(
        "forgot_password",
        TemplateView.as_view(template_name="frontend/placeholder.html", extra_context={"title": "Recuperar Senha"}),
        name="forgot_password",
    ),
    # Área logada (SPA): as 5 abas da navbar.
    path("", app_page("home", "Início", views.HomeView), name="home"),
    path("equipe", app_page("team", "Minha Equipe", views.TeamView), name="team"),
    path("recharge", views.DepositView.as_view(tab="deposit", title="Depositar Saldo Pix",
                                              page_template="frontend/app/pages/recharge.html"), name="deposit"),
    path("recharge/<str:charge_id>", views.DepositPaymentView.as_view(
        tab="deposit", title="Pagamento Pix", page_template="frontend/app/pages/recharge_payment.html"),
        name="deposit_payment"),
    path("record", views.PurchasesView.as_view(tab="purchases", title="Minhas Compras",
                                             page_template="frontend/app/pages/purchases.html"), name="purchases"),
    path("my", app_page("profile", "Meu Perfil", views.ProfileView), name="profile"),  # mesmo path do site original
    path("extrato", views.StatementPageView.as_view(tab="statement", title="Extrato de Movimentações",
                                                     page_template="frontend/app/pages/statement_page.html"),
         name="statement_page"),
    path("withdraw/history", views.WithdrawHistoryView.as_view(
        tab="profile", title="Histórico de Saques", page_template="frontend/app/pages/withdraw_history.html"),
        name="withdraw_history"),
    path("withdraw", views.WithdrawView.as_view(tab="profile", title="Solicitar Saque Pix",
                                                page_template="frontend/app/pages/withdraw.html"), name="withdraw"),
    # Tela do time (is_staff): prévia do cartão da fila, dentro do app e na aba Perfil.
    # "painel/" e não "admin/": o /admin/ é do Django admin, que vem antes no ROOT_URLCONF e engoliria o path.
    path("painel/fila", views.StaffWithdrawQueueView.as_view(
        tab="profile", title="Fila de Saque (time)",
        page_template="frontend/app/pages/admin_withdraw_queue.html"), name="admin_withdraw_queue"),
    # Ações do Início (POST + JSON).
    path("acoes/check-in", views.CheckinActionView.as_view(), name="action_checkin"),
    path("acoes/bonus", views.BonusActionView.as_view(), name="action_bonus"),
    path("acoes/roleta", views.RouletteActionView.as_view(), name="action_roulette"),
    path("acoes/saque", views.WithdrawActionView.as_view(), name="action_withdraw"),
    path("acoes/saque/fila", views.WithdrawQueueView.as_view(), name="action_withdraw_queue"),
    path("acoes/cpf", views.CpfActionView.as_view(), name="action_cpf"),
    path("acoes/extrato", views.StatementView.as_view(), name="statement"),
    path("acoes/notificacoes", views.NotificationsView.as_view(), name="notifications"),
    path("acoes/notificacoes/lidas", views.NotificationsReadView.as_view(), name="notifications_read"),
    path("acoes/deposito", views.DepositActionView.as_view(), name="action_deposit"),
    path("acoes/deposito/<str:charge_id>/status", views.DepositStatusView.as_view(), name="action_deposit_status"),
    path("acoes/chave-pix", views.PixKeyActionView.as_view(), name="action_pix_key"),
    path("acoes/senha", views.PasswordChangeActionView.as_view(), name="action_password"),
    path("acoes/processo-seletivo", views.RecruitActionView.as_view(), name="action_recruit"),
    path("acoes/equipamentos/<slug:product_id>/ativar", views.PurchaseActionView.as_view(), name="action_purchase"),
    # Logout só por POST (padrão do Django), com CSRF.
    path("logout", LogoutView.as_view(next_page="frontend:login"), name="logout"),
    # dentro de urlpatterns:

    path("vip", views.VipView.as_view(tab="profile", title="Plano VIP",
                                    page_template="frontend/app/pages/vip.html"), name="vip"),
    path("vip/pagamento/<str:transaction_id>", views.VipPaymentView.as_view(
        tab="profile", title="Pagamento VIP",
        page_template="frontend/app/pages/vip_payment.html"), name="vip_payment"),

    path("acoes/vip", views.VipActionView.as_view(), name="action_vip"),
    path("acoes/vip/<str:transaction_id>/status", views.VipStatusView.as_view(), name="action_vip_status"),

    path("webhooks/pixzy/vip", views.PixzyVipWebhookView.as_view(), name="webhook_pixzy_vip"),
]
