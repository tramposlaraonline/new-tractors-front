from django.conf import settings
from django.db import models


class DemoWithdrawBalance(models.Model):
    """Saldo para saque de DEMONSTRAÇÃO (FRONTEND_DEMO_WITHDRAW): valor fictício, exibido com selo.

    Guarda só quando o usuário viu o saldo pela primeira vez; o valor é calculado a partir daí
    (ver preview/demo_withdraw.py). Nada é gravado a cada aumento.
    """

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="demo_withdraw")
    started_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "saldo de demonstração"
        verbose_name_plural = "saldos de demonstração"

    def __str__(self):
        return f"Demonstração de {self.user}"
