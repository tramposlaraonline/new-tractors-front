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


class DemoQueuedWithdrawal(models.Model):
    """Saque NA FILA de um usuário de demonstração, criado pelo manage.py seed_queue.

    Cada linha é um pedido gravado na base, com dono e horário de chegada, e é o que a fila conta para
    dizer a posição de cada um: a tela mostra sempre a contagem real dos pedidos criados antes do
    pedido do usuário, nunca um número fixo, estimado ou inflado.
    """

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="demo_queued_withdrawals")
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=8, default="pending")  # pending | paid
    created_at = models.DateTimeField()
    settled_at = models.DateTimeField(null=True, blank=True)  # quando saiu da fila (relógio que sobrevive a reinício)

    class Meta:
        verbose_name = "saque de demonstração na fila"
        verbose_name_plural = "saques de demonstração na fila"
        indexes = [models.Index(fields=["status", "created_at", "id"], name="demo_queue_pending")]

    def __str__(self):
        return f"Fila de demonstração: {self.user} — {self.amount}"
