from pathlib import Path
from datetime import timedelta
import os

BASE_DIR = Path(__file__).resolve().parent.parent

# SECRET_KEY: previously a literal committed to git history — anyone with repo
# access (or who found this in the public GitHub repo) has always been able to
# read it. Now sourced from env var; the literal below is kept ONLY as a local-
# dev fallback so `manage.py runserver` still works without extra setup.
# ACTION NEEDED: set DJANGO_SECRET_KEY in the PythonAnywhere env config, and
# rotate this value (generate a fresh one) since the old one is permanently
# compromised by having been in git history.
SECRET_KEY = os.environ.get(
    'DJANGO_SECRET_KEY',
    'django-insecure-q(r5cb59^oj(27g8&#d68c5!l!!h+r7s+2*#m-mfkq9toc6k1k',
)

# DEBUG: was hardcoded True, meaning any unhandled 500 (a bad request, a bug in
# a new endpoint, anything) rendered Django's debug page — full stack trace,
# local variable values, installed apps, and settings — to whoever triggered it,
# no login required. Defaults to False now. If PythonAnywhere breaks after this
# deploy and you need debug output temporarily, set DJANGO_DEBUG=True in the env
# config rather than editing this file again.
DEBUG = os.environ.get('DJANGO_DEBUG', 'False') == 'True'

# Kept as a wildcard since the actual PythonAnywhere hostname isn't known here —
# narrowing this blindly could break the live deployment. Recommend replacing
# "*" with the real hostname (e.g. "yourapp.pythonanywhere.com") once confirmed.
ALLOWED_HOSTS = ["*"]

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'rest_framework_simplejwt.token_blacklist',
    'corsheaders',
    'core',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

CSRF_TRUSTED_ORIGINS = [
    'https://*.trycloudflare.com',
    'https://undateable-ima-facetious.ngrok-free.dev',
    'http://localhost:8000',
    'http://127.0.0.1:8000',
]

# ─── Django REST Framework ────────────────────────────────────────────────────
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'core.authentication.PasswordChangeEnforcingJWTAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
    # Fix 2: Pagination — prevents huge unfiltered dumps as data grows
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 100,   # 100 is safe for now; lower to 50 when course list grows beyond 200
    # Rate limiting on credential-guessing endpoints. LoginView had zero
    # protection against brute-forcing a password — unlimited attempts, no
    # lockout, no delay. Scoped (not global) so it only affects the specific
    # views that opt in via throttle_scope, not every anonymous request.
    'DEFAULT_THROTTLE_CLASSES': (
        'rest_framework.throttling.ScopedRateThrottle',
    ),
    'DEFAULT_THROTTLE_RATES': {
        'login': '10/min',            # per IP — generous for real typos, blocks brute force
        'change_password': '10/min',
    },
}

# ─── JWT Token Lifetimes ──────────────────────────────────────────────────────
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME':  timedelta(hours=8),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'ROTATE_REFRESH_TOKENS':       True,
    # BLACKLIST_AFTER_ROTATION must be True whenever ROTATE_REFRESH_TOKENS
    # is True. Without it, rotation issues a new refresh token but never
    # invalidates the old one — a stolen refresh token stays usable forever
    # regardless of how many times the legitimate user rotates it.
    # token_blacklist app was added in commit 7192e62; this activates it.
    'BLACKLIST_AFTER_ROTATION':    True,
}

# ─── CORS ─────────────────────────────────────────────────────────────────────
# CORS_ALLOWED_ORIGINS previously did nothing — CORS_ALLOW_ALL_ORIGINS=True below
# it overrode the allowlist entirely, so ANY origin could make authenticated
# cross-origin requests (cookies aside, this still meant any website could hit
# the API using a token it stole via other means, or ride on a user's browser
# session for token-based flows). Flipped to a real allowlist.
#
# Included the same origins already trusted for CSRF further up (the
# trycloudflare/ngrok tunnel domains) since those are evidently in active use
# for some deployment/demo flow. If the production frontend is served from a
# domain not listed here, requests from it will start failing CORS after this
# deploy — add that origin below, or temporarily set CORS_ALLOW_ALL_ORIGINS=True
# in the PythonAnywhere env config while confirming the right domain.
CORS_ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
]
CORS_ALLOWED_ORIGIN_REGEXES = [
    r"^https://.*\.trycloudflare\.com$",
]
CORS_ALLOW_ALL_ORIGINS = os.environ.get('CORS_ALLOW_ALL_ORIGINS', 'False') == 'True'

# ─── Static files ─────────────────────────────────────────────────────────────
# STATIC_URL must stay '/static/' — Django admin templates hardcode this path
# and there is no supported override. The previous '/assets/' setting caused
# all admin CSS/JS to 404, rendering the admin panel as unstyled HTML.
STATIC_URL = '/static/'
# Frontend build assets (Vite outputs to dist/assets) are included here if
# the build directory exists. collectstatic pulls them into STATIC_ROOT too.
STATICFILES_DIRS = [
    os.path.join(BASE_DIR, 'dist', 'assets'),
] if os.path.exists(os.path.join(BASE_DIR, 'dist', 'assets')) else []
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')

ROOT_URLCONF = 'obe.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [os.path.join(BASE_DIR, 'dist')],
        'APP_DIRS': False,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
            'loaders': [
                'django.template.loaders.filesystem.Loader',
                'django.template.loaders.app_directories.Loader',
            ],
        },
    },
]

# ─── Account provisioning ──────────────────────────────────────────────────────
# Shared temp password assigned to newly-provisioned accounts (students, instructors).
# Override via env var in production so it isn't a static, guessable value forever.
# Every account created with this password must also get must_change_password=True
# (enforced server-side in core/authentication.py) — the temp password alone is not
# a security boundary, the forced-rotation gate is.
DEFAULT_TEMP_PASSWORD = os.environ.get('DEFAULT_TEMP_PASSWORD', 'IqraSecurePass2026!')

AUTH_USER_MODEL = 'core.User'
WSGI_APPLICATION = 'obe.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
