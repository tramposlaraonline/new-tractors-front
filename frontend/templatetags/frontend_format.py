from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from django import template
from django.templatetags.static import static

register = template.Library()


@register.filter
def asset_url(path):
    """Imagem vinda do backend: URL absoluta/raiz passa direto; caminho relativo vira arquivo estático."""
    path = str(path or "")
    if path.startswith(("http://", "https://", "/")):
        return path
    return static(path)


@register.filter
def brl(value):
    """Formata valor em reais no padrão do site: 1234.5 -> "R$ 1.234,50"; -3 -> "-R$ 3,00".

    Valor ausente ou inválido vira "R$ 0,00" (nunca quebra a tela por causa de um saldo).
    """
    try:
        amount = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, TypeError, ValueError):
        amount = Decimal("0.00")
    sign = "-" if amount < 0 else ""
    integer, cents = f"{abs(amount):.2f}".split(".")
    integer = f"{int(integer):,}".replace(",", ".")
    return f"{sign}R$ {integer},{cents}"


@register.filter
def phone_br(value):
    """Celular só com dígitos -> "(82) 99102-8518". Fora do padrão, devolve como veio."""
    digits = "".join(ch for ch in str(value or "") if ch.isdigit())
    if digits.startswith("55") and len(digits) in (12, 13):
        digits = digits[2:]
    if len(digits) == 11:
        return f"({digits[:2]}) {digits[2:7]}-{digits[7:]}"
    if len(digits) == 10:
        return f"({digits[:2]}) {digits[2:6]}-{digits[6:]}"
    return str(value or "")


@register.filter
def brl_short(value):
    """Valor redondo sem centavos: 1000 -> "R$ 1.000" (com centavos, cai no formato completo)."""
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return brl(value)
    if amount != amount.to_integral_value():
        return brl(amount)
    return "R$ " + f"{int(amount):,}".replace(",", ".")


@register.filter
def signed_brl(value):
    """+R$ 0,50 / -R$ 5,00 (extrato)."""
    text = brl(value)
    return text if text.startswith("-") or text == "R$ 0,00" else "+" + text


@register.filter
def cents(value):
    """Decimal em reais -> inteiro em centavos (para o JS calcular sem ponto flutuante)."""
    try:
        return int((Decimal(str(value)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    except (InvalidOperation, TypeError, ValueError):
        return 0


@register.filter
def day_label(value):
    """"Hoje, 00:31" / "Ontem, 23:35" / "18/09/2026, 22:45" no fuso do projeto."""
    from datetime import timedelta
    from django.utils import timezone
    if not value:
        return ""
    local = timezone.localtime(value) if timezone.is_aware(value) else value
    today = timezone.localdate()
    hour = local.strftime("%H:%M")
    if local.date() == today:
        return f"Hoje, {hour}"
    if local.date() == today - timedelta(days=1):
        return f"Ontem, {hour}"
    return local.strftime("%d/%m/%Y, %H:%M")


@register.filter
def ago(value):
    """Tempo relativo das notificações: "Agora", "Há 19 min", "Há 23 horas", "Ontem" ou "18/09/2026"."""
    from datetime import timedelta
    from django.utils import timezone
    if not value:
        return ""
    now = timezone.now()
    seconds = max(0, int((now - value).total_seconds()))
    if seconds < 60:
        return "Agora"
    if seconds < 3600:
        return f"Há {seconds // 60} min"
    if seconds < 86400:
        hours = seconds // 3600
        return f"Há {hours} hora" if hours == 1 else f"Há {hours} horas"
    local = timezone.localtime(value)
    if local.date() == timezone.localdate() - timedelta(days=1):
        return "Ontem"
    return local.strftime("%d/%m/%Y")


@register.filter
def count_suffix(value):
    """" (6)" quando há itens; vazio quando zero (como os filtros do site)."""
    return f" ({value})" if value else ""
