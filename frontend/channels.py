"""Links de atendimento/comunidade: vêm do Django admin (CommunicationChannels) com cache de 60s.

Se um campo estiver vazio no admin, usa as settings antigas como reserva:
FRONTEND_WHATSAPP_URL / FRONTEND_TELEGRAM_URL (suporte) e FRONTEND_SUPPORT_URL (central genérica).
"""
from django.conf import settings
from django.core.cache import cache
from django.db import DatabaseError

from .models import CHANNELS_CACHE_KEY, CommunicationChannels

FIELDS = ("support_whatsapp", "support_telegram", "community_whatsapp", "community_telegram")
CACHE_SECONDS = 60


def _from_admin():
    data = cache.get(CHANNELS_CACHE_KEY)
    if data is None:
        try:
            obj = CommunicationChannels.objects.filter(pk=1).first()
        except DatabaseError:  # tabela ainda não migrada: não derruba o site
            obj = None
        data = {f: (getattr(obj, f) if obj else "") for f in FIELDS}
        cache.set(CHANNELS_CACHE_KEY, data, CACHE_SECONDS)
    return data


def get_channels():
    data = dict(_from_admin())
    data["support_whatsapp"] = data["support_whatsapp"] or getattr(settings, "FRONTEND_WHATSAPP_URL", "")
    data["support_telegram"] = data["support_telegram"] or getattr(settings, "FRONTEND_TELEGRAM_URL", "")
    data["support_url"] = getattr(settings, "FRONTEND_SUPPORT_URL", "")
    data["has_community"] = bool(data["community_whatsapp"] or data["community_telegram"])
    return data
