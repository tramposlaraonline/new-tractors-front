"""Validações de dados de identificação e Pix (usadas pelas views; o backend do projeto deve revalidar)."""
import re

EMAIL_RE = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")
RANDOM_KEY_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
NAME_RE = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿ' .-]+")


def only_digits(value):
    return re.sub(r"\D", "", value or "")


def cpf_is_valid(digits):
    if len(digits) != 11 or digits == digits[0] * 11:
        return False
    for size in (9, 10):
        total = sum(int(digits[i]) * (size + 1 - i) for i in range(size))
        if (total * 10) % 11 % 10 != int(digits[size]):
            return False
    return True


def cnpj_is_valid(digits):
    if len(digits) != 14 or digits == digits[0] * 14:
        return False
    for size in (12, 13):
        weights = list(range(size - 7, 1, -1)) + list(range(9, 1, -1))
        total = sum(int(d) * w for d, w in zip(digits[:size], weights))
        check = 0 if total % 11 < 2 else 11 - total % 11
        if check != int(digits[size]):
            return False
    return True


def format_cpf(digits):
    return f"{digits[:3]}.{digits[3:6]}.{digits[6:9]}-{digits[9:]}"


def mask_cpf(digits):
    return f"***.{digits[3:6]}.{digits[6:9]}-**"


def clean_full_name(raw):
    """Nome e sobrenome, só letras. Devolve (nome, erro)."""
    name = " ".join((raw or "").split())
    if len(name) < 5 or " " not in name or len(name) > 100 or not NAME_RE.fullmatch(name):
        return None, "Informe o nome completo do titular."
    return name, None


def clean_cpf(raw):
    digits = only_digits(raw)
    if not cpf_is_valid(digits):
        return None, "CPF inválido. Confira os números."
    return digits, None


PIX_KEY_TYPES = ("cpf", "cnpj", "phone", "email", "random")


def clean_pix_key(key_type, raw):
    """Normaliza a chave conforme o tipo. Devolve (chave, erro)."""
    raw = (raw or "").strip()
    if key_type == "cpf":
        return clean_cpf(raw)
    if key_type == "cnpj":
        digits = only_digits(raw)
        if not cnpj_is_valid(digits):
            return None, "CNPJ inválido. Confira os números."
        return digits, None
    if key_type == "phone":
        digits = only_digits(raw)
        if digits.startswith("55") and len(digits) in (12, 13):
            digits = digits[2:]
        if len(digits) != 11:
            return None, "Telefone deve ter DDD + 9 dígitos."
        return digits, None
    if key_type == "email":
        email = raw.lower()
        if len(email) > 77 or not EMAIL_RE.fullmatch(email):
            return None, "E-mail inválido."
        return email, None
    if key_type == "random":
        key = raw.lower()
        if not RANDOM_KEY_RE.fullmatch(key):
            return None, "Chave aleatória inválida (formato 00000000-0000-0000-0000-000000000000)."
        return key, None
    return None, "Selecione o tipo de chave."
