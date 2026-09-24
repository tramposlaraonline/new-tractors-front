from urllib.parse import urlparse

from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import models

CHANNELS_CACHE_KEY = "frontend:channels"

WHATSAPP_HOSTS = {"wa.me", "api.whatsapp.com", "chat.whatsapp.com", "whatsapp.com", "www.whatsapp.com"}
TELEGRAM_HOSTS = {"t.me", "telegram.me", "www.t.me"}


def _check_host(value, hosts, example):
    parsed = urlparse(value or "")
    if parsed.scheme != "https" or (parsed.hostname or "").lower() not in hosts:
        raise ValidationError(f"Use um link https válido. Ex.: {example}")


# Funções de módulo (a migração precisa conseguir importá-las pelo nome).
def validate_whatsapp(value):
    _check_host(value, WHATSAPP_HOSTS, "https://wa.me/5511999999999 ou https://chat.whatsapp.com/CODIGO")


def validate_telegram(value):
    _check_host(value, TELEGRAM_HOSTS, "https://t.me/usuario ou https://t.me/+CODIGO")


class CommunicationChannels(models.Model):
    """Links de atendimento e de comunidade exibidos no site (registro único, editado pelo Django admin)."""

    support_whatsapp = models.URLField(
        "WhatsApp do suporte", blank=True, validators=[validate_whatsapp],
        help_text="Número de atendimento. Ex.: https://wa.me/5511999999999")
    support_telegram = models.URLField(
        "Telegram do suporte", blank=True, validators=[validate_telegram],
        help_text="Usuário ou número de atendimento. Ex.: https://t.me/usuario_suporte")
    community_whatsapp = models.URLField(
        "Comunidade no WhatsApp", blank=True, validators=[validate_whatsapp],
        help_text="Grupo ou canal para os leads entrarem. Ex.: https://chat.whatsapp.com/CODIGO")
    community_telegram = models.URLField(
        "Comunidade no Telegram", blank=True, validators=[validate_telegram],
        help_text="Grupo ou canal para os leads entrarem. Ex.: https://t.me/+CODIGO")
    updated_at = models.DateTimeField("Atualizado em", auto_now=True)

    class Meta:
        verbose_name = "Links de atendimento e comunidade"
        verbose_name_plural = "Links de atendimento e comunidade"

    def __str__(self):
        return "Links de atendimento e comunidade"

    def save(self, *args, **kwargs):
        self.pk = 1  # registro único
        super().save(*args, **kwargs)
        cache.delete(CHANNELS_CACHE_KEY)

    def delete(self, *args, **kwargs):
        cache.delete(CHANNELS_CACHE_KEY)
        return super().delete(*args, **kwargs)
