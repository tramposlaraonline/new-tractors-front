"""Pontos de integração com o backend real do projeto.

O app `frontend` só desenha as telas; os números vêm destas funções. No projeto real, aponte a
setting correspondente para uma função sua (caminho pontilhado), sem editar este arquivo:

    FRONTEND_WALLET_PROVIDER = "carteira.services.resumo_para_frontend"
    FRONTEND_HEADER_PROVIDER = "notificacoes.services.estado_do_cabecalho"
    FRONTEND_CHECKIN_PROVIDER = "beneficios.services.estado_do_checkin"
    FRONTEND_PRODUCTS_PROVIDER = "maquinas.services.catalogo_para_frontend"
    FRONTEND_HEADER_PROVIDER também pode devolver "plan_name" (ex.: "Plano Ouro", mostrado no menu lateral).
"""
from decimal import Decimal

from django.conf import settings
from django.utils.module_loading import import_string


def default_wallet_summary(user):
    """Saldos do card "Meu Patrimônio". Valores em reais (Decimal)."""
    return {"invest_balance": Decimal("0"), "withdraw_balance": Decimal("0")}


def default_header_state(user):
    """Estado do cabeçalho: `has_unread_notifications` liga o ponto dourado do sino."""
    return {"has_unread_notifications": False}


def default_checkin_state(user):
    """Check-in diário: `done_today` troca o botão pelo aviso "Check-in realizado hoje"."""
    return {"done_today": False}


def _call(setting_name, default, user):
    path = getattr(settings, setting_name, None)
    return (import_string(path) if path else default)(user)


def get_wallet_summary(user):
    data = _call("FRONTEND_WALLET_PROVIDER", default_wallet_summary, user)
    invest = Decimal(data.get("invest_balance") or 0)
    withdraw = Decimal(data.get("withdraw_balance") or 0)
    # "Meu Patrimônio" = saldo para investir + saldo para saque (confere nos dois prints do site no ar).
    return {"invest_balance": invest, "withdraw_balance": withdraw, "total_balance": invest + withdraw}


def get_demo_withdraw(user):
    """Saldo para saque de DEMONSTRAÇÃO, ou None quando FRONTEND_DEMO_WITHDRAW_PROVIDER não está configurado.

    O provider devolve {"balance": Decimal, "rate_per_hour": Decimal}; o Início mostra o valor subindo a cada
    3s a partir daí, sempre com o selo "Demonstração — valores fictícios".
    """
    path = getattr(settings, "FRONTEND_DEMO_WITHDRAW_PROVIDER", None)
    if not path:
        return None
    data = import_string(path)(user)
    return {"balance": Decimal(data["balance"]), "rate_per_hour": Decimal(data["rate_per_hour"])}


def default_products(user):
    from .catalog import PRODUCTS
    return PRODUCTS


def get_products(user):
    """Máquinas do Início. Cada item: id, code, description, price, daily_credit, period_days, image
    (caminho estático ou URL absoluta). O crédito total previsto é calculado: diário × dias do período."""
    products = []
    for item in _call("FRONTEND_PRODUCTS_PROVIDER", default_products, user):
        daily = Decimal(item["daily_credit"])
        days = int(item["period_days"])
        products.append({**item, "price": Decimal(item["price"]), "daily_credit": daily, "period_days": days,
                         "total_credit": daily * days})
    return products


def get_checkin_state(user):
    return {"done_today": False, **_call("FRONTEND_CHECKIN_PROVIDER", default_checkin_state, user)}


def get_header_state(user):
    return {"has_unread_notifications": False, **_call("FRONTEND_HEADER_PROVIDER", default_header_state, user)}


def default_roulette_state(user):
    """Roda da Sorte: quantos giros o usuário tem."""
    return {"spins_available": 0}


def get_roulette_state(user):
    state = {"spins_available": 0, **_call("FRONTEND_ROULETTE_PROVIDER", default_roulette_state, user)}
    state["spins_available"] = max(0, int(state["spins_available"] or 0))
    return state


# =========================================================================
# AÇÕES (POST). Cada setting aponta para uma função do projeto real que
# executa a operação de verdade e devolve um dict com "ok" (+ campos abaixo):
#
#   FRONTEND_CHECKIN_ACTION(user)                         -> {"ok"}
#   FRONTEND_BONUS_ACTION(user, code)                     -> {"ok", "amount"}
#   FRONTEND_ROULETTE_ACTION(user)                        -> {"ok", "prize_amount", "segment_index" (0-6)}
#   FRONTEND_PURCHASE_ACTION(user, product_id, idempotency_key) -> {"ok", "spins_awarded"}
#
# Em falha de regra de negócio: {"ok": False, "message": "texto para o usuário"}.
# A função do projeto é quem garante saldo, unicidade do bônus, limite de giros e
# idempotência da compra (a mesma idempotency_key nunca pode cobrar duas vezes).
# =========================================================================
UNAVAILABLE = {"ok": False, "message": "Função indisponível no momento. Tente novamente mais tarde."}


def run_action(setting_name, user, **kwargs):
    path = getattr(settings, setting_name, None)
    if not path:
        return dict(UNAVAILABLE)
    return dict(import_string(path)(user, **kwargs) or {})

def default_profile_state(user):
    """Perfil: `avatar_url` vazio usa a foto padrão; `pix_linked` mostra o selo "Vinculada" na Conta Pix."""
    return {"avatar_url": "", "pix_linked": False, "account_active": True}


def get_profile_state(user):
    return {**default_profile_state(user), **_call("FRONTEND_PROFILE_PROVIDER", default_profile_state, user)}


# =========================================================================
# SAQUE PIX
#   FRONTEND_WITHDRAW_PROVIDER(user) -> {
#       "pix_key": {"holder_name", "key_type" (phone|cpf|cnpj|email|random), "key", "document"} ou None,
#       "fee_percent": Decimal, "min_amount": Decimal, "settlement": str,
#       "recent": [{"amount": Decimal, "created_at": datetime, "status": review|processing|paid|completed|failed|refunded}]
#   }
#   FRONTEND_WITHDRAW_ACTION(user, amount, idempotency_key) -> {"ok", "message"?}
#   A função do projeto debita o saldo de forma atômica, bloqueia saque simultâneo e nunca processa
#   duas vezes a mesma idempotency_key.
# =========================================================================
PIX_KEY_TYPES = {"phone": "Telefone", "cpf": "CPF", "cnpj": "CNPJ", "email": "E-mail", "random": "Aleatória"}  # noqa: E501
WITHDRAW_STATUS = {
    "review": ("Em revisão manual", "warn"), "processing": ("Em processamento", "warn"),
    "paid": ("Pago", "ok"), "completed": ("Concluído", "ok"),
    "failed": ("Recusado", "bad"), "refunded": ("Estornado", "bad"),
}


def default_withdraw_state(user):
    return {"pix_key": None, "fee_percent": Decimal("10"), "min_amount": Decimal("5"),
            "settlement": "Instantâneo", "recent": []}


def get_withdraw_state(user):
    data = {**default_withdraw_state(user), **_call("FRONTEND_WITHDRAW_PROVIDER", default_withdraw_state, user)}
    key = data.get("pix_key")
    if key:
        key = {**key, "type_label": PIX_KEY_TYPES.get(key.get("key_type"), str(key.get("key_type") or "").upper())}
    recent = []
    for item in (data.get("recent") or [])[:10]:
        label, tone = WITHDRAW_STATUS.get(item.get("status"), ("Em processamento", "warn"))
        recent.append({**item, "amount": Decimal(item["amount"]),
                       "status_label": item.get("status_label") or label, "tone": tone})
    return {**data, "pix_key": key, "recent": recent,
            "fee_percent": Decimal(data["fee_percent"]), "min_amount": Decimal(data["min_amount"])}


# =========================================================================
# DEPÓSITO PIX, CPF DO TITULAR E CHAVE PIX DE SAQUE
#   FRONTEND_DEPOSIT_PROVIDER(user) -> {"min_amount", "max_amount", "presets": [..], "cpf_registered": bool,
#                                       "cpf_masked": "***.456.789-**"}
#   FRONTEND_DEPOSIT_CHARGE_PROVIDER(user, charge_id) -> {"amount", "pix_code", "qr_image"?, "expires_at", "status"}
#       ou None. ATENÇÃO: deve filtrar pelo usuário (nunca devolver cobrança de outra pessoa).
#   Ações: FRONTEND_CPF_ACTION(user, cpf)
#          FRONTEND_DEPOSIT_ACTION(user, amount, idempotency_key) -> {"ok", "charge_id"}
#          FRONTEND_DEPOSIT_STATUS(user, charge_id, manual_check) -> {"ok", "status": pending|paid|expired}
#          FRONTEND_PIX_KEY_ACTION(user, key_type, key)   (titular/documento vêm do cadastro do usuário)
# =========================================================================
def default_deposit_state(user):
    return {"min_amount": Decimal("25"), "max_amount": Decimal("50000"),
            "presets": [Decimal(v) for v in (50, 150, 300, 500, 1000, 2000)],
            "cpf_registered": False, "cpf_masked": ""}


def get_deposit_state(user):
    data = {**default_deposit_state(user), **_call("FRONTEND_DEPOSIT_PROVIDER", default_deposit_state, user)}
    return {**data, "min_amount": Decimal(data["min_amount"]), "max_amount": Decimal(data["max_amount"]),
            "presets": [Decimal(v) for v in data["presets"]]}


def get_deposit_charge(user, charge_id):
    path = getattr(settings, "FRONTEND_DEPOSIT_CHARGE_PROVIDER", None)
    return import_string(path)(user, charge_id) if path else None


# =========================================================================
# MINHAS COMPRAS (/record)
#   FRONTEND_PURCHASES_PROVIDER(user) -> [{
#       "contract_id", "product_id", "code", "image"? (padrão: foto do catálogo), "amount", "daily_credit",
#       "started_at": datetime, "ends_at": datetime, "accumulated", "next_credit_at": datetime|None,
#       "status": active|finished }]
# =========================================================================
def default_purchases(user):
    return []


def get_purchases(user):
    from .catalog import PRODUCTS
    images = {p["id"]: p["image"] for p in PRODUCTS}
    contracts = []
    for item in _call("FRONTEND_PURCHASES_PROVIDER", default_purchases, user) or []:
        contracts.append({
            **item,
            "amount": Decimal(item["amount"]), "daily_credit": Decimal(item["daily_credit"]),
            "accumulated": Decimal(item.get("accumulated") or 0),
            "image": item.get("image") or images.get(item.get("product_id"), ""),
            "is_active": item.get("status", "active") == "active",
        })
    active = [c for c in contracts if c["is_active"]]
    summary = {
        "total_amount": sum((c["amount"] for c in active), Decimal("0")),
        "daily_total": sum((c["daily_credit"] for c in active), Decimal("0")),
        "active_count": len(active),
        "accumulated_total": sum((c["accumulated"] for c in contracts), Decimal("0")),
    }
    return {"contracts": contracts, "summary": summary}


# =========================================================================
# EQUIPE (/equipe)
#   FRONTEND_TEAM_PROVIDER(user) -> {
#     "invite_code": str,
#     "commissions_total": Decimal,
#     "levels": [{"level": 1, "percent": Decimal, "members": int, "active": int, "volume": Decimal, "credited": Decimal}, ...],
#     "members": [{"name", "phone", "joined_at": datetime, "level": 1|2|3, "active": bool, "invested": Decimal}],
#     "goals": [{"prize": Decimal, "invites_done": int, "invites_target": int, "volume_done": Decimal,
#                "volume_target": Decimal, "status": claimed|in_progress, "claimed_at": datetime|None}],
#   }
#   Totais (membros, ativos, taxa de ativação, volume) são calculados a partir dos níveis.
# =========================================================================
LEVEL_NAMES = {1: "Diretos", 2: "Indiretos", 3: "3ª Geração"}


def default_team(user):
    return {"invite_code": "", "commissions_total": Decimal("0"), "levels": [], "members": [], "goals": []}


def _pct(done, target):
    if not target:
        return 100
    return max(0, min(100, int(Decimal(done) * 100 / Decimal(target))))


def get_team(user):
    data = {**default_team(user), **_call("FRONTEND_TEAM_PROVIDER", default_team, user)}
    levels = []
    for lv in data["levels"]:
        levels.append({**lv, "percent": Decimal(lv["percent"]), "volume": Decimal(lv["volume"]),
                       "credited": Decimal(lv["credited"]), "name": LEVEL_NAMES.get(lv["level"], "")})
    members_total = sum(lv["members"] for lv in levels)
    active_total = sum(lv["active"] for lv in levels)
    goals = []
    for g in data["goals"]:
        inv_done, inv_target = int(g["invites_done"]), int(g["invites_target"])
        vol_done, vol_target = Decimal(g["volume_done"]), Decimal(g["volume_target"])
        goals.append({**g, "prize": Decimal(g["prize"]), "volume_done": vol_done, "volume_target": vol_target,
                      "invites_pct": _pct(inv_done, inv_target), "volume_pct": _pct(vol_done, vol_target),
                      "invites_missing": max(0, inv_target - inv_done),
                      "volume_missing": max(Decimal("0"), vol_target - vol_done),
                      "claimed": g.get("status") == "claimed"})
    members = [{**m, "invested": Decimal(m.get("invested") or 0)} for m in data["members"]]
    return {
        "invite_code": data["invite_code"],
        "commissions_total": Decimal(data["commissions_total"]),
        "levels": levels,
        "members": members,
        "members_total": members_total,
        "active_total": active_total,
        "activation_rate": round(active_total * 100 / members_total) if members_total else 0,
        "network_volume": sum((lv["volume"] for lv in levels), Decimal("0")),
        "goals": goals,
    }


# =========================================================================
# NOTIFICAÇÕES (sino)
#   FRONTEND_NOTIFICATIONS_PROVIDER(user, offset, limit) -> [{"id", "title", "body", "created_at": datetime,
#       "read": bool, "time_label"?: str (ex.: "Hoje", substitui o "Há X min")}], da mais nova para a mais antiga.
#   FRONTEND_NOTIFICATIONS_READ_ACTION(user) -> {"ok"}   (marca todas como lidas)
#   O ponto dourado do sino continua vindo de FRONTEND_HEADER_PROVIDER.has_unread_notifications.
# =========================================================================
def get_notifications(user, offset=0, limit=50):
    path = getattr(settings, "FRONTEND_NOTIFICATIONS_PROVIDER", None)
    return list(import_string(path)(user, offset, limit) or []) if path else []


# =========================================================================
# HISTÓRICO DE SAQUES (/withdraw/history)
#   FRONTEND_WITHDRAW_HISTORY_PROVIDER(user) -> [{"id", "amount", "fee", "net", "created_at", "settled_at"|None,
#       "status": review|processing|paid|completed|failed|refunded}], do mais novo para o mais antigo.
# =========================================================================
WITHDRAW_GROUPS = {"paid": "done", "completed": "done", "review": "processing", "processing": "processing",
                   "failed": "other", "refunded": "other"}


def get_withdraw_history(user):
    path = getattr(settings, "FRONTEND_WITHDRAW_HISTORY_PROVIDER", None)
    rows = list(import_string(path)(user) or []) if path else []
    items = []
    for row in rows:
        group = WITHDRAW_GROUPS.get(row.get("status"), "processing")
        label = {"done": "Pago", "processing": "Processando", "other": WITHDRAW_STATUS.get(row.get("status"), ("Cancelado",))[0]}[group]
        items.append({**row, "amount": Decimal(row["amount"]), "fee": Decimal(row.get("fee") or 0),
                      "net": Decimal(row.get("net") if row.get("net") is not None else row["amount"]),
                      "group": group, "status_label": label})
    done = [i for i in items if i["group"] == "done"]
    counts = {"all": len(items), "done": len(done),
              "processing": sum(1 for i in items if i["group"] == "processing"),
              "other": sum(1 for i in items if i["group"] == "other")}
    return {"items": items, "counts": counts, "net_paid": sum((i["net"] for i in done), Decimal("0"))}
