from django.contrib import admin
from django.shortcuts import redirect
from django.urls import reverse

from .models import CommunicationChannels


@admin.register(CommunicationChannels)
class CommunicationChannelsAdmin(admin.ModelAdmin):
    """Registro único: a lista leva direto ao formulário de edição."""

    fieldsets = [
        ("Suporte (botão Chat, fone do cabeçalho, Perfil)", {"fields": ["support_whatsapp", "support_telegram"]}),
        ("Comunidade (modais de boas-vindas e de login/cadastro)", {"fields": ["community_whatsapp", "community_telegram"]}),
    ]
    readonly_fields = ["updated_at"]

    def has_add_permission(self, request):
        return not CommunicationChannels.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        obj = CommunicationChannels.objects.first()
        if obj:
            return redirect(reverse("admin:frontend_communicationchannels_change", args=[obj.pk]))
        return redirect(reverse("admin:frontend_communicationchannels_add"))
