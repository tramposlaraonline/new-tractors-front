"""Projeto Django mínimo para visualizar e testar o app `frontend`, e o que roda no Render.

Local: nada de variável de ambiente, SQLite e DEBUG ligado (como sempre foi).
No Render (variável `RENDER` presente): DEBUG desligado, SECRET_KEY/DATABASE_URL obrigatórias,
estáticos pelo WhiteNoise. No projeto real, basta copiar a pasta `frontend/` (ver README).
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

ON_RENDER = "RENDER" in os.environ

# No Render falta a chave = erro na subida (KeyError), nunca uma chave padrão em produção.
SECRET_KEY = os.environ["DJANGO_SECRET_KEY"] if ON_RENDER else "preview-only-not-for-production"
DEBUG = not ON_RENDER

ALLOWED_HOSTS = ["localhost", "127.0.0.1", "testserver"]
# Hostname *.onrender.com (o Render define) + domínios próprios separados por vírgula.
PUBLIC_HOSTS = [h.strip() for h in [os.environ.get("RENDER_EXTERNAL_HOSTNAME", ""),
                                    *os.environ.get("DJANGO_ALLOWED_HOSTS", "").split(",")] if h.strip()]
ALLOWED_HOSTS += PUBLIC_HOSTS
CSRF_TRUSTED_ORIGINS = [f"https://{h}" for h in PUBLIC_HOSTS]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.messages",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.staticfiles",
    "frontend",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "preview.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

if ON_RENDER:
    import dj_database_url

    DATABASES = {"default": dj_database_url.parse(os.environ["DATABASE_URL"], conn_max_age=600,
                                                  conn_health_checks=True)}
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "preview.sqlite3",
        }
    }

LANGUAGE_CODE = "pt-br"
TIME_ZONE = "America/Sao_Paulo"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

if ON_RENDER:
    # WhiteNoise logo depois do SecurityMiddleware; nomes com hash + gzip/brotli, cache longo.
    MIDDLEWARE.insert(1, "whitenoise.middleware.WhiteNoiseMiddleware")
    STORAGES = {
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
    }
    # O Render termina o TLS na borda (e já força https); o app só precisa confiar no header.
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 3600
    SECURE_CONTENT_TYPE_NOSNIFF = True
    # Sem DEBUG, erro 500 só aparece nos logs se o logger mandar para o console.
    LOGGING = {
        "version": 1,
        "disable_existing_loggers": False,
        "handlers": {"console": {"class": "logging.StreamHandler"}},
        "root": {"handlers": ["console"], "level": "WARNING"},
    }

LOGIN_URL = "frontend:login"
LOGIN_REDIRECT_URL = "/"

# Trava temporária de login e cadastro (aviso "temporariamente indisponível"). False libera.
FRONTEND_AUTH_LOCKED = True

# Dados fictícios para o preview (no projeto real, apontar para os serviços de verdade).
FRONTEND_WALLET_PROVIDER = "preview.demo_data.wallet_summary"
FRONTEND_HEADER_PROVIDER = "preview.demo_data.header_state"
FRONTEND_CHECKIN_PROVIDER = "preview.demo_data.checkin_state"
FRONTEND_ROULETTE_PROVIDER = "preview.demo_data.roulette_state"
FRONTEND_CHECKIN_ACTION = "preview.demo_data.checkin"
FRONTEND_BONUS_ACTION = "preview.demo_data.redeem_bonus"
FRONTEND_ROULETTE_ACTION = "preview.demo_data.spin_roulette"
FRONTEND_PURCHASE_ACTION = "preview.demo_data.purchase"
FRONTEND_PROFILE_PROVIDER = "preview.demo_data.profile_state"
FRONTEND_WITHDRAW_PROVIDER = "preview.demo_data.withdraw_state"
FRONTEND_WITHDRAW_ACTION = "preview.demo_data.withdraw"
FRONTEND_DEPOSIT_PROVIDER = "preview.demo_data.deposit_state"
FRONTEND_DEPOSIT_CHARGE_PROVIDER = "preview.demo_data.deposit_charge"
FRONTEND_CPF_ACTION = "preview.demo_data.register_cpf"
FRONTEND_DEPOSIT_ACTION = "preview.demo_data.create_deposit"
FRONTEND_DEPOSIT_STATUS = "preview.demo_data.deposit_status"
FRONTEND_PIX_KEY_ACTION = "preview.demo_data.register_pix_key"
FRONTEND_PURCHASES_PROVIDER = "preview.demo_data.purchases"
FRONTEND_STATEMENT_PROVIDER = "preview.demo_data.statement"
FRONTEND_TEAM_PROVIDER = "preview.demo_data.team"
FRONTEND_STATEMENT_SUMMARY_PROVIDER = "preview.demo_data.statement_summary"
FRONTEND_NOTIFICATIONS_PROVIDER = "preview.demo_data.notifications"
FRONTEND_NOTIFICATIONS_READ_ACTION = "preview.demo_data.mark_notifications_read"
FRONTEND_WITHDRAW_HISTORY_PROVIDER = "preview.demo_data.withdraw_history"
FRONTEND_RECRUIT_ACTION = "preview.demo_data.recruit"
# Links de suporte/comunidade: editar no Django admin (/admin/ → "Links de atendimento e comunidade").
