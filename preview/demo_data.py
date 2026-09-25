"""Dados e ações fictícios só para o preview local (estado em memória, some ao reiniciar o servidor).

Valores iniciais iguais aos prints. Código de bônus de teste: NEW2026 (R$ 2,60, uma vez por usuário).
"""
import random
import secrets
import threading
from collections import namedtuple
from datetime import timedelta
from decimal import Decimal

from django.db.models import Sum
from django.utils import timezone

from frontend.catalog import PRODUCTS

from .models import DemoQueuedWithdrawal

ROULETTE_PRIZES = [Decimal(v) for v in ("1.00", "2.50", "10.00", "0.50", "5.00", "1.50", "3.00")]
DEMO_BONUS = {"NEW2026": Decimal("2.60")}

_lock = threading.Lock()
_state = {}


def _get(user):
    s = _state.setdefault(user.pk, {
        "invest": Decimal("10.20"), "withdraw": Decimal("5.00"), "checked_in": False, "spins": 1,
        "used_codes": set(), "purchases": {},
    })
    if "withdrawals" not in s:
        now = timezone.now()
        s["withdrawals"] = [{"amount": Decimal("5.00"), "created_at": now - timedelta(days=d), "status": "completed"}
                            for d in (7, 6, 5)]
        s["withdraw_keys"] = {}
    if "contracts" not in s:
        # Um contrato de exemplo, como no print (NW354 ativo há 2 dias).
        start = timezone.now() - timedelta(days=2, hours=1, minutes=56)
        s["contracts"] = [{"contract_id": 27616, "product_id": "nw354", "code": "NW354", "amount": Decimal("25"),
                           "daily_credit": Decimal("5"), "started_at": start, "ends_at": start + timedelta(days=16),
                           "accumulated": Decimal("10"), "next_credit_at": start + timedelta(days=3),
                           "status": "active"}]
    if "charges" not in s:
        s.update(cpf=None, pix_key=None, charges={}, deposit_keys={})
    if "ledger" not in s:
        now = timezone.now()
        seed = [
            (6, 2, "bonus", "Bônus de cadastro", "Bonificação creditada na conta", "5.00"),
            (6, 1.9, "checkin", "Recompensa Diária (Check-in)", "Bônus diário de presença", "0.50"),
            (5, 0, "deposit", "Depósito PIX Instantâneo", "Transferência recebida via Pix", "25.00"),
            (5, -0.1, "purchase", "Compra de plano: NW354", "Ativação de equipamento", "-25.00"),
            (5, -0.2, "withdraw", "Saque PIX para Conta", "Liquidação efetuada via Banco Central", "-5.00"),
            (1, 3, "bonus", "Bônus: AGROPOP", "Bonificação creditada na conta", "2.10"),
            (1, 2, "yield", "Rendimento Diário: NW354", "Crédito automático do equipamento", "5.00"),
        ] + [(1, h / 10, "commission", "Comissão por Indicação", "Bônus referente à sua equipe", v)
             for h, v in ((5, "0.50"), (8, "4.50"), (12, "1.00"), (15, "0.25"), (18, "20.00"), (21, "0.50"))]
        s["ledger"] = [{"id": i, "kind": k, "title": title, "description": desc, "amount": Decimal(v),
                        "created_at": now - timedelta(days=d, hours=h), "status": "completed"}
                       for i, (d, h, k, title, desc, v) in enumerate(seed)]
    return s


def _log(s, kind, title, description, amount, status="completed"):
    entry = {"id": len(s["ledger"]), "kind": kind, "title": title, "description": description,
             "amount": Decimal(amount), "created_at": timezone.now(), "status": status}
    s["ledger"].append(entry)
    return entry


def wallet_summary(user):
    s = _get(user)
    return {"invest_balance": s["invest"], "withdraw_balance": s["withdraw"]}


def header_state(user):
    return {"has_unread_notifications": any(not n["read"] for n in notifications(user, 0, 50)),
            "plan_name": "Plano Ouro"}


def checkin_state(user):
    return {"done_today": _get(user)["checked_in"]}


def roulette_state(user):
    return {"spins_available": _get(user)["spins"]}


def checkin(user):
    with _lock:
        s = _get(user)
        if s["checked_in"]:
            return {"ok": False, "message": "Você já fez o check-in de hoje."}
        s["checked_in"] = True
        s["withdraw"] += Decimal("0.50")
        _log(s, "checkin", "Recompensa Diária (Check-in)", "Bônus diário de presença", "0.50")
    return {"ok": True, "amount": Decimal("0.50")}


def redeem_bonus(user, code):
    with _lock:
        s = _get(user)
        if code not in DEMO_BONUS or code in s["used_codes"]:
            return {"ok": False, "message": "Código inválido ou já utilizado."}
        s["used_codes"].add(code)
        s["withdraw"] += DEMO_BONUS[code]
        _log(s, "bonus", f"Bônus: {code}", "Bonificação creditada na conta", DEMO_BONUS[code])
        return {"ok": True, "amount": DEMO_BONUS[code]}


def spin_roulette(user):
    with _lock:
        s = _get(user)
        if s["spins"] < 1:
            return {"ok": False, "message": "Você não tem giros disponíveis."}
        index = random.randrange(len(ROULETTE_PRIZES))
        s["spins"] -= 1
        s["withdraw"] += ROULETTE_PRIZES[index]
        _log(s, "roulette", "Prêmio da Roda da Sorte", "Recompensa creditada no saldo", ROULETTE_PRIZES[index])
        return {"ok": True, "prize_amount": ROULETTE_PRIZES[index], "segment_index": index}


def purchase(user, product_id, idempotency_key):
    with _lock:
        s = _get(user)
        if idempotency_key in s["purchases"]:  # mesmo clique repetido: devolve o resultado anterior, sem cobrar de novo
            return s["purchases"][idempotency_key]
        product = next(p for p in PRODUCTS if p["id"] == product_id)
        if s["invest"] < product["price"]:
            return {"ok": False, "message": "Saldo para investir insuficiente para ativar este equipamento."}
        s["invest"] -= product["price"]
        s["spins"] += 1
        _log(s, "purchase", f"Compra de plano: {product['code']}", "Ativação de equipamento", -product["price"])
        now = timezone.now()
        s["contracts"].append({"contract_id": random.randint(10000, 99999), "product_id": product["id"],
                               "code": product["code"], "amount": product["price"],
                               "daily_credit": product["daily_credit"], "started_at": now,
                               "ends_at": now + timedelta(days=product["period_days"]), "accumulated": Decimal("0"),
                               "next_credit_at": now + timedelta(days=1), "status": "active"})
        result = {"ok": True, "spins_awarded": 1}
        s["purchases"][idempotency_key] = result
        return result


def profile_state(user):
    return {"pix_linked": bool(_get(user)["pix_key"])}


REVIEW_SECONDS = 30  # demo: a fila paga um saque a cada 30s, na ordem de chegada
DAILY_PAYOUT_LIMIT = Decimal("3000.00")  # demo: teto de liquidação por dia. É ele que segura uma fila grande:
# sem um limite, qualquer pedido com mais de REVIEW_SECONDS de idade seria pago assim que a tela abrisse.
_payout = {"last_at": None}  # quando o último saque da fila foi pago (a fila semeada guarda o seu em settled_at)

# Um item da fila: "memory" é o dicionário do saque em memória (preview) e "pk" a linha da fila semeada
# na base (manage.py seed_queue). Só um dos dois existe em cada item.
Pending = namedtuple("Pending", "created_at uid amount memory pk")


def _pending():
    """Saques aguardando pagamento de TODOS os usuários, na ordem de chegada (created_at, usuário).

    Junta a fila em memória (os saques que este preview recebeu) com a fila semeada na base
    (manage.py seed_queue). As duas entram na mesma contagem: por isso a posição do cartão é a
    quantidade real de pedidos criados antes do pedido do usuário, e não um número separado.
    """
    rows = [Pending(w["created_at"], uid, w["amount"], w, None)
            for uid, s in _state.items() for w in s.get("withdrawals", ()) if w["status"] == "review"]
    rows += [Pending(created_at=c, uid=u, amount=a, memory=None, pk=i)
             for c, u, a, i in DemoQueuedWithdrawal.objects.filter(status="pending")
             .order_by("created_at", "id").values_list("created_at", "user_id", "amount", "id")]
    rows.sort(key=lambda row: (row.created_at, row.uid, row.pk is not None))
    return rows


def _last_paid_at():
    """Quando a fila pagou o último saque: em memória e na base, para o relógio da fila não voltar
    a zero quando o servidor reinicia (senão a fila semeada inteira cairia de uma vez)."""
    from_db = DemoQueuedWithdrawal.objects.filter(status="paid").exclude(settled_at=None)\
        .order_by("-settled_at").values_list("settled_at", flat=True).first()
    return max((at for at in (_payout["last_at"], from_db) if at is not None), default=None)


def _paid_today(start, end):
    """Quanto a fila já liquidou hoje (na base e em memória), para não estourar o limite diário."""
    total = DemoQueuedWithdrawal.objects.filter(status="paid", settled_at__gte=start, settled_at__lt=end)\
        .aggregate(total=Sum("amount"))["total"] or Decimal("0")
    return total + sum((w["amount"] for s in _state.values() for w in s.get("withdrawals", ())
                        if w["status"] == "paid" and w.get("settled_at") and start <= w["settled_at"] < end),
                       Decimal("0"))


def _settle_queue():
    """Paga a fila em ordem: cada saque sai REVIEW_SECONDS depois do anterior (ou do próprio pedido, se chegou
    depois), enquanto couber no limite diário de liquidação. Devolve o que sobrou na fila, para quem só queria
    a posição não ler a fila toda de novo."""
    now = timezone.now()
    day_start = timezone.localtime(now).replace(hour=0, minute=0, second=0, microsecond=0)
    budget = DAILY_PAYOUT_LIMIT - _paid_today(day_start, day_start + timedelta(days=1))
    last = _last_paid_at()
    rows = _pending()
    paid = 0
    for row in rows:
        if row.amount > budget:
            break  # limite do dia acabou: a fila só anda amanhã
        paid_at = max(row.created_at, last) + timedelta(seconds=REVIEW_SECONDS) if last else \
            row.created_at + timedelta(seconds=REVIEW_SECONDS)
        if paid_at > now:
            break
        budget -= row.amount
        paid += 1
        if row.pk is not None:
            DemoQueuedWithdrawal.objects.filter(pk=row.pk).update(status="paid", settled_at=paid_at)
        else:
            row.memory["status"] = "paid"
            row.memory["settled_at"] = paid_at
            if row.memory.get("ledger"):
                row.memory["ledger"].update(status="completed", description="Liquidação efetuada via Banco Central")
        _payout["last_at"] = last = paid_at
    return rows[paid:]


def withdraw_queue(user):
    """FRONTEND_WITHDRAW_QUEUE_PROVIDER do preview: posição contada na fila acima, nunca inventada."""
    with _lock:
        for index, row in enumerate(_settle_queue()):
            if row.uid == user.pk:
                return {"position": index + 1, "amount": row.amount, "requested_at": row.created_at,
                        "entry_position": row.memory.get("entry_position") if row.memory else None}
    return None


def withdraw_state(user):
    with _lock:
        s = _get(user)
        _settle_queue()
        return {"pix_key": s["pix_key"], "recent": list(reversed(s["withdrawals"]))}


def withdraw(user, amount, idempotency_key):
    with _lock:
        s = _get(user)
        if idempotency_key in s["withdraw_keys"]:
            return s["withdraw_keys"][idempotency_key]
        _settle_queue()
        if any(w["status"] == "review" for w in s["withdrawals"]):
            return {"ok": False,
                    "message": "Você já possui um saque em processamento. Aguarde a conclusão para solicitar outro."}
        if amount > s["withdraw"]:
            return {"ok": False, "message": "Saldo insuficiente para este saque."}
        s["withdraw"] -= amount
        entry = _log(s, "withdraw", "Saque PIX para Conta", "Em análise / processamento", -amount, "processing")
        s["withdrawals"].append({"amount": amount, "created_at": timezone.now(), "status": "review", "ledger": entry,
                                 "entry_position": len(_pending()) + 1})
        result = {"ok": True}
        s["withdraw_keys"][idempotency_key] = result
        return result


# ---------------------------------------------------------------- CPF, chave Pix e depósito (demo)
DEMO_PIX_KEY = "pagamentos@newtractors.invalid"  # chave fictícia: o QR do preview não é pagável


def _emv(field_id, value):
    return f"{field_id}{len(value):02d}{value}"


def _crc16(payload):
    crc = 0xFFFF
    for byte in payload.encode():
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) if crc & 0x8000 else crc << 1
            crc &= 0xFFFF
    return f"{crc:04X}"


def _brcode(amount, txid):
    """Pix copia e cola no padrão EMV do Banco Central (com CRC), só para a demonstração."""
    account = _emv("00", "br.gov.bcb.pix") + _emv("01", DEMO_PIX_KEY)
    payload = (_emv("00", "01") + _emv("26", account) + _emv("52", "0000") + _emv("53", "986")
               + _emv("54", f"{amount:.2f}") + _emv("58", "BR") + _emv("59", "NEW TRACTORS DEMO")
               + _emv("60", "SAO PAULO") + _emv("62", _emv("05", txid[:25])) + "6304")
    return payload + _crc16(payload)


def deposit_state(user):
    s = _get(user)
    cpf = s["cpf"]
    return {"cpf_registered": bool(cpf), "cpf_masked": f"***.{cpf[3:6]}.{cpf[6:9]}-**" if cpf else ""}


def register_cpf(user, cpf):
    with _lock:
        _get(user)["cpf"] = cpf
    return {"ok": True}


def register_pix_key(user, key_type, key):
    with _lock:
        s = _get(user)
        cpf = s["cpf"] or "52998224725"
        s["pix_key"] = {"holder_name": user.get_full_name() or user.get_username(), "key_type": key_type, "key": key,
                        "document": f"{cpf[:3]}.{cpf[3:6]}.{cpf[6:9]}-{cpf[9:]}"}
    return {"ok": True}


def recruit(user, message):
    return {"ok": True}


def create_deposit(user, amount, idempotency_key):
    with _lock:
        s = _get(user)
        if idempotency_key in s["deposit_keys"]:
            return s["deposit_keys"][idempotency_key]
        charge_id = secrets.token_hex(8)
        s["charges"][charge_id] = {"amount": amount, "pix_code": _brcode(amount, charge_id), "status": "pending",
                                   "created_at": timezone.now(), "expires_at": timezone.now() + timedelta(minutes=15)}
        result = {"ok": True, "charge_id": charge_id}
        s["deposit_keys"][idempotency_key] = result
        return result


def deposit_charge(user, charge_id):
    charge = _get(user)["charges"].get(charge_id)  # só cobranças deste usuário
    if charge and charge["status"] == "pending" and timezone.now() > charge["expires_at"]:
        charge["status"] = "expired"
    return charge


def deposit_status(user, charge_id, manual_check):
    """Demo: o "Já fiz o Pix" confirma o pagamento (3s depois de gerar); a consulta automática só observa."""
    with _lock:
        charge = deposit_charge(user, charge_id)
        if not charge:
            return {"ok": False, "message": "Cobrança não encontrada."}
        elapsed = (timezone.now() - charge["created_at"]).total_seconds()
        if charge["status"] == "pending" and manual_check and elapsed >= 3:
            charge["status"] = "paid"
            _get(user)["invest"] += charge["amount"]
            _log(_get(user), "deposit", "Depósito PIX Instantâneo", "Transferência recebida via Pix", charge["amount"])
        return {"ok": True, "status": charge["status"]}


def purchases(user):
    return list(reversed(_get(user)["contracts"]))


def statement(user, kinds, offset, limit):
    with _lock:
        s = _get(user)
        _settle_queue()
        items = [e for e in s["ledger"] if kinds is None or e["kind"] in kinds]
        items.sort(key=lambda e: e["created_at"], reverse=True)
        return [dict(e) for e in items[offset:offset + limit]]


def team(user):
    from datetime import datetime
    now = timezone.now()
    day = timezone.make_aware(datetime(2026, 9, 19, 10, 0))
    members = [
        ("MARIA ROSANETE FRANK", "66997127059", 1, True, "25"),
        ("Jeovane Silva do Nascimento", "66981007210", 1, False, "0"),
        ("Carlos Eduardo Lima", "66984412233", 2, True, "50"),
        ("Patrícia Souza", "66991123344", 2, True, "25"),
        ("Rafael Moreira", "66992234455", 2, False, "0"),
        ("Luana Ferreira", "66993345566", 2, True, "50"),
        ("Diego Martins", "66994456677", 2, True, "50"),
        ("Aline Costa", "66995567788", 2, False, "0"),
        ("José Raul", "18996262943", 3, True, "2025"),
        ("Edicar aparecido Malaquias Cardoso", "18997301150", 3, False, "0"),
        ("gabriela gomes da silva", "69993629200", 3, True, "150"),
        ("MICHAEL SIMAO FRANK", "69992526863", 3, True, "25"),
        ("Adriana Viana", "66981304892", 3, True, "25"),
        ("Bruno Teixeira", "66982415503", 3, False, "0"),
        ("Camila Rocha", "66983526614", 3, False, "0"),
        ("Fernando Alves", "66984637725", 3, False, "0"),
        ("Juliana Prado", "66985748836", 3, False, "0"),
    ]
    goals = [(10, 1, 1, 100, "claimed", 19), (15, 5, 5, 500, "claimed", 21), (30, 20, 20, 5000, "claimed", 22),
             (50, 9, 30, 8000, "in_progress", None), (100, 9, 40, 15000, "in_progress", None),
             (180, 9, 60, 25000, "in_progress", None), (350, 9, 100, 50000, "in_progress", None),
             (800, 9, 200, 120000, "in_progress", None)]
    return {
        "invite_code": "2LK7QX",
        "commissions_total": Decimal("30.25"),
        "levels": [
            {"level": 1, "percent": 18, "members": 2, "active": 1, "volume": Decimal("25"), "credited": Decimal("4.50")},
            {"level": 2, "percent": 2, "members": 6, "active": 4, "volume": Decimal("175"), "credited": Decimal("3.50")},
            {"level": 3, "percent": 1, "members": 9, "active": 4, "volume": Decimal("2225"), "credited": Decimal("22.25")},
        ],
        "members": [{"name": n, "phone": p, "joined_at": day, "level": lv, "active": a, "invested": Decimal(v)}
                    for n, p, lv, a, v in members],
        "goals": [{"prize": Decimal(pr), "invites_done": d, "invites_target": t, "volume_done": Decimal("2425"),
                   "volume_target": Decimal(vt), "status": st,
                   "claimed_at": timezone.make_aware(datetime(2026, 9, cd, 12)) if cd else None}
                  for pr, d, t, vt, st, cd in goals],
    }


# ---------------------------------------------------------------- notificações, resumo do extrato, saques (demo)
def _notification_for(e):
    v = e["amount"]
    brl = "R$ " + f"{abs(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    kind = e["kind"]
    if kind == "yield":
        return "Rendimentos creditados com sucesso!", f"Foram creditados {brl} referentes ao seu equipamento {e['title'].split(': ')[-1]}."
    if kind == "withdraw":
        if e["status"] != "completed":
            return None
        return "Saque PIX Transferido com Sucesso", f"Transferência de {brl} liquidada via Banco Central para sua chave cadastrada."
    if kind == "commission":
        return "Comissão por Indicação Creditada", f"Você recebeu {brl} referente à comissão da sua equipe."
    if kind == "bonus" and "cadastro" in e["title"]:
        return "Bônus de Boas-Vindas Creditado", f"Boas-vindas à plataforma New Tractors! O bônus de {brl} foi creditado na sua conta."
    if kind == "bonus":
        return "Bônus Resgatado", f"O bônus de {brl} foi creditado na sua conta."
    if kind == "checkin":
        return "Recompensa de Presença Recebida", f"Bônus diário de {brl} creditado no seu saldo."
    if kind == "deposit":
        return "Depósito PIX Confirmado!", f"Recarga de {brl} aprovada e creditada no seu saldo para investir."
    if kind == "purchase":
        return "Equipamento Ativado", f"{e['title']} (#{e['id'] + 50000}) no valor de {brl}."
    if kind == "roulette":
        return "Prêmio da Roda da Sorte", f"Você ganhou {brl} na Roda da Sorte."
    return None


def notifications(user, offset, limit):
    s = _get(user)
    read_until = s.get("notif_read_until")
    items = []
    for e in s["ledger"]:
        text = _notification_for(e)
        if text:
            items.append({"id": f"l{e['id']}", "title": text[0], "body": text[1], "created_at": e["created_at"],
                          "read": bool(read_until and e["created_at"] <= read_until)})
    for cid, c in s["charges"].items():
        brl = "R$ " + f"{c['amount']:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        items.append({"id": f"c{cid}", "title": "Depósito PIX Gerado",
                      "body": f"Solicitação de recarga de {brl} aguardando pagamento via PIX.",
                      "created_at": c["created_at"], "read": bool(read_until and c["created_at"] <= read_until)})
    items.sort(key=lambda n: n["created_at"], reverse=True)
    if not s["checked_in"]:
        items.insert(0, {"id": "daily", "title": "Recompensa diária disponível!",
                         "body": "Seu bônus de presença de R$ 0,50 está pronto para coleta. Acesse seu perfil para coletar.",
                         "created_at": timezone.now(), "read": False, "time_label": "Hoje"})
    return items[offset:offset + limit]


def mark_notifications_read(user):
    with _lock:
        _get(user)["notif_read_until"] = timezone.now()
    return {"ok": True}


def statement_summary(user):
    from frontend.statement import FILTERS
    s = _get(user)
    counts = {key: sum(1 for e in s["ledger"] if kinds is None or e["kind"] in kinds) for key, _, kinds in FILTERS}
    income = sum((e["amount"] for e in s["ledger"] if e["kind"] in {"yield", "checkin", "commission", "bonus"}), Decimal("0"))
    deposits = sum((e["amount"] for e in s["ledger"] if e["kind"] == "deposit"), Decimal("0"))
    return {"count": counts["all"], "income_total": income, "deposit_total": deposits, "counts": counts}


def withdraw_history(user):
    with _lock:
        s = _get(user)
        _settle_queue()
        rows = []
        for i, w in enumerate(s["withdrawals"]):
            fee = (w["amount"] * Decimal("0.10")).quantize(Decimal("0.01"))
            done = w["status"] in ("paid", "completed")
            rows.append({"id": 56370 + i * 7919, "amount": w["amount"], "fee": fee, "net": w["amount"] - fee,
                         "created_at": w["created_at"], "status": w["status"],
                         "settled_at": w["created_at"] + timedelta(minutes=1) if done else None})
        return list(reversed(rows))
