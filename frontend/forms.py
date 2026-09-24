import re

from django import forms
from django.contrib.auth import authenticate, get_user_model, password_validation
from django.db import IntegrityError, transaction

# Mensagens iguais às do agrofarm-auth.js original.
GENERIC_LOGIN_ERROR = "Credenciais inválidas."
PHONE_TAKEN_ERROR = "Este telefone já possui cadastro."


def mobile_to_username(digits):
    """Converte o celular (só dígitos, sem +55) no `username` usado pelo backend de auth.

    Ponto único de adaptação: se o projeto guardar o telefone como "+5511987654321",
    ou num campo diferente, ajuste aqui.
    """
    return digits


def normalize_phone(value):
    """Só dígitos, sem o +55 quando o número vem colado com o código do país."""
    digits = re.sub(r"\D", "", value or "")
    if digits.startswith("55") and len(digits) in (12, 13):
        digits = digits[2:]
    return digits


def apply_invitation_code(user, code):
    """Gancho para o projeto real tratar o código de convite (indicação, vínculo etc.).

    Recebe o código já normalizado (sem espaços, maiúsculo) ou "" quando não informado.
    Roda na mesma transação da criação do usuário.
    """


class PhoneLoginForm(forms.Form):
    mobile = forms.CharField(
        label="Telefone Celular",
        max_length=20,
        error_messages={"required": "Informe seu número de telefone."},
    )
    password = forms.CharField(
        label="Senha de Acesso",
        strip=False,
        max_length=128,
        error_messages={"required": "Informe sua senha de acesso."},
    )

    def __init__(self, request=None, *args, **kwargs):
        self.request = request
        self.user_cache = None
        super().__init__(*args, **kwargs)

    def clean_mobile(self):
        # Aceita o número colado com o código do país (+55), como o original.
        digits = normalize_phone(self.cleaned_data["mobile"])
        if not 8 <= len(digits) <= 11:
            raise forms.ValidationError("Telefone deve ter entre 8 e 11 dígitos.")
        return digits

    def clean(self):
        cleaned = super().clean()
        mobile = cleaned.get("mobile")
        password = cleaned.get("password")
        if mobile and password:
            user = authenticate(self.request, username=mobile_to_username(mobile), password=password)
            # Mensagem genérica: não revela se o telefone existe nem se a conta está inativa.
            if user is None or not user.is_active:
                raise forms.ValidationError(GENERIC_LOGIN_ERROR, code="invalid_login")
            self.user_cache = user
        return cleaned

    def get_user(self):
        return self.user_cache


class RegisterForm(forms.Form):
    full_name = forms.CharField(
        label="Nome Completo",
        max_length=150,
        error_messages={"required": "Informe seu nome e sobrenome."},
    )
    phone = forms.CharField(
        label="Telefone Celular com DDD",
        max_length=20,
        error_messages={"required": "Telefone deve ter 11 dígitos com DDD."},
    )
    password = forms.CharField(
        label="Senha de Acesso",
        strip=False,
        max_length=128,
        error_messages={"required": "A senha deve ter no mínimo 6 caracteres."},
    )
    password_confirmation = forms.CharField(
        label="Confirmar Senha",
        strip=False,
        max_length=128,
        error_messages={"required": "Confirme sua senha."},
    )
    invitation_code = forms.CharField(label="Código de Convite", max_length=32, required=False)

    def clean_full_name(self):
        name = " ".join(self.cleaned_data["full_name"].split())
        if len(name) < 3:
            raise forms.ValidationError("Informe seu nome e sobrenome.")
        return name

    def clean_phone(self):
        digits = normalize_phone(self.cleaned_data["phone"])
        if len(digits) != 11:
            raise forms.ValidationError("Telefone deve ter 11 dígitos com DDD.")
        if get_user_model().objects.filter(username=mobile_to_username(digits)).exists():
            raise forms.ValidationError(PHONE_TAKEN_ERROR, code="phone_taken")
        return digits

    def clean_password(self):
        password = self.cleaned_data["password"]
        if len(password) < 6:
            raise forms.ValidationError("A senha deve ter no mínimo 6 caracteres.")
        return password

    def clean_invitation_code(self):
        return re.sub(r"\s+", "", self.cleaned_data["invitation_code"]).upper()

    def clean(self):
        cleaned = super().clean()
        password = cleaned.get("password")
        confirmation = cleaned.get("password_confirmation")
        if password and confirmation and password != confirmation:
            self.add_error("password_confirmation", "As senhas não coincidem.")
        if password and "password" not in self.errors:
            # Validadores do projeto (AUTH_PASSWORD_VALIDATORS); sem nenhum configurado, não faz nada.
            first, _, last = cleaned.get("full_name", "").partition(" ")
            probe = get_user_model()(
                username=mobile_to_username(cleaned.get("phone") or ""), first_name=first, last_name=last
            )
            try:
                password_validation.validate_password(password, probe)
            except forms.ValidationError as exc:
                self.add_error("password", exc)
        return cleaned

    def save(self):
        """Cria o usuário. Devolve None se o telefone foi cadastrado em paralelo (erro já anexado ao form)."""
        data = self.cleaned_data
        first, _, last = data["full_name"].partition(" ")
        try:
            with transaction.atomic():
                user = get_user_model().objects.create_user(
                    username=mobile_to_username(data["phone"]),
                    password=data["password"],
                    first_name=first[:150],
                    last_name=last[:150],
                )
                apply_invitation_code(user, data["invitation_code"])
        except IntegrityError:
            self.add_error("phone", forms.ValidationError(PHONE_TAKEN_ERROR, code="phone_taken"))
            return None
        return user
