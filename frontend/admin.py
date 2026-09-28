from django.contrib import admin
from django.shortcuts import redirect
from django.urls import reverse

from .models import CommunicationChannels, UserProfile, DepositCharge, VipCharge


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

@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "cpf", "is_vip", "invest_balance", "withdraw_balance")
    search_fields = ("user__username", "cpf")

@admin.register(DepositCharge)
class DepositChargeAdmin(admin.ModelAdmin):
    list_display = ("transaction_id", "user", "amount_cents", "status", "created_at", "paid_at")
    list_filter = ("status",)
    search_fields = ("transaction_id", "user__username")

@admin.register(VipCharge)
class VipChargeAdmin(admin.ModelAdmin):
    list_display = ("transaction_id", "user", "amount_cents", "status", "created_at", "paid_at")
    list_filter = ("status",)