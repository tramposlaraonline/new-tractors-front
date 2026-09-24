"""Extrato de movimentações: categorias dos filtros, ícones e normalização dos lançamentos.

FRONTEND_STATEMENT_PROVIDER(user, kinds, offset, limit) -> lista de lançamentos, do mais novo para o mais antigo:
    {"id", "kind", "title", "description", "amount": Decimal (negativo = saída), "created_at": datetime,
     "status": completed|processing|failed}
`kinds` é um conjunto de tipos (filtro escolhido) ou None (Todos). O provedor deve filtrar e paginar no banco.
"""
from decimal import Decimal

from django.conf import settings
from django.utils.module_loading import import_string

# Filtros do modal (ordem e nomes iguais ao site).
FILTERS = [
    ("all", "Todos", None),
    ("income", "Rendimentos & Bônus", {"yield", "checkin", "commission", "bonus"}),
    ("roulette", "Roleta", {"roulette"}),
    ("deposit", "Depósitos", {"deposit"}),
    ("withdraw", "Saques", {"withdraw"}),
]
FILTER_KINDS = {key: kinds for key, _, kinds in FILTERS}

STATUS = {"completed": ("Concluido", "ok"), "processing": ("Processando", "warn"), "failed": ("Recusado", "bad")}


def _svg(paths):
    return ('<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" '
            f'stroke-linejoin="round" aria-hidden="true">{paths}</svg>')


TREND = _svg('<polyline points="22 7 13.5 15.5 8.5 10.5 2 17"/><polyline points="16 7 22 7 22 13"/>')
ICONS = {
    "yield": (TREND, "green"),
    "commission": (TREND, "green"),
    "bonus": (TREND, "green"),
    "checkin": (_svg('<rect width="18" height="18" x="3" y="4" rx="2"/><path d="M16 2v4"/><path d="M8 2v4"/>'
                     '<path d="M3 10h18"/>'), "green"),
    "roulette": (_svg('<circle cx="12" cy="8" r="6"/><path d="m15.477 12.89 1.515 8.526a.5.5 0 0 1-.81.47l-3.58-2.687'
                      'a1 1 0 0 0-1.197 0l-3.586 2.686a.5.5 0 0 1-.81-.469l1.514-8.526"/>'), "gold"),
    "deposit": (_svg('<path d="m7 7 10 10"/><path d="M17 7v10H7"/>'), "green"),
    "withdraw": (_svg('<path d="M7 7h10v10"/><path d="M7 17 17 7"/>'), "red"),
    "purchase": (_svg('<path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"/><path d="M14 2v4a2 2 0 0 0 2 2h4"/>'
                      '<path d="M10 9H8"/><path d="M16 13H8"/><path d="M16 17H8"/>'), "gray"),
}


def get_statement(user, filter_key, offset, limit):
    path = getattr(settings, "FRONTEND_STATEMENT_PROVIDER", None)
    if not path:
        return []
    items = []
    for item in import_string(path)(user, FILTER_KINDS.get(filter_key), offset, limit) or []:
        icon, tone = ICONS.get(item.get("kind"), ICONS["purchase"])
        label, status_tone = STATUS.get(item.get("status"), STATUS["processing"])
        items.append({**item, "amount": Decimal(item["amount"]), "icon": icon, "icon_tone": tone,
                      "status_label": label, "status_tone": status_tone,
                      "page_title": PAGE_TITLES.get(item.get("kind"), item.get("title")),
                      "page_tag": PAGE_TAGS.get(item.get("kind"), ""), "page_status": page_status_label(item)})
    return items


# Página "Extrato de Movimentações" (/extrato): título curto, etiqueta e status por tipo.
PAGE_TITLES = {"withdraw": "Saque Pix", "deposit": "Depósito Pix"}
PAGE_TAGS = {
    "withdraw": "Transferência Pix", "deposit": "Pix recebido", "yield": "Rendimento", "commission": "Indicação",
    "bonus": "Bônus", "checkin": "Check-in", "roulette": "Roleta", "purchase": "Equipamento",
}


def page_status_label(item):
    if item.get("status") == "completed":
        return "Pago" if item.get("kind") == "withdraw" else "Concluído"
    return STATUS.get(item.get("status"), STATUS["processing"])[0]


def get_statement_summary(user):
    """FRONTEND_STATEMENT_SUMMARY_PROVIDER(user) -> {"count", "income_total", "deposit_total",
    "counts": {"all": n, "income": n, "roulette": n, "deposit": n, "withdraw": n}}"""
    path = getattr(settings, "FRONTEND_STATEMENT_SUMMARY_PROVIDER", None)
    data = import_string(path)(user) if path else {}
    counts = {key: int((data.get("counts") or {}).get(key) or 0) for key, _, _ in FILTERS}
    return {"count": int(data.get("count") or counts["all"]), "income_total": Decimal(data.get("income_total") or 0),
            "deposit_total": Decimal(data.get("deposit_total") or 0), "counts": counts}
