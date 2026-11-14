import os
import sys
from pathlib import Path
from urllib.parse import urlparse
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BASE_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if 'test' not in sys.argv:
    load_dotenv(PROJECT_ROOT / '.env', override=True)
    load_dotenv(BASE_DIR / '.env', override=True)
else:
    load_dotenv(BASE_DIR / '.env', override=False)
SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', 'dev-only-change-me-before-deploying')
DEBUG = os.environ.get('DJANGO_DEBUG', '0') == '1'
if not DEBUG and 'test' not in sys.argv and SECRET_KEY == 'dev-only-change-me-before-deploying':
    raise RuntimeError('Set DJANGO_SECRET_KEY in production')
ALLOWED_HOSTS = os.environ.get('DJANGO_ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',')
CSRF_TRUSTED_ORIGINS = [v for v in os.environ.get('DJANGO_CSRF_TRUSTED_ORIGINS', '').split(',') if v]
if DEBUG:
    CSRF_TRUSTED_ORIGINS += ['http://127.0.0.1:5173', 'http://localhost:5173', 'http://127.0.0.1:4173', 'http://localhost:4173']

INSTALLED_APPS = [
    'django.contrib.admin', 'django.contrib.auth', 'django.contrib.contenttypes',
    'django.contrib.sessions', 'django.contrib.messages', 'django.contrib.staticfiles',
    'rest_framework', 'core.apps.CoreConfig',
]
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]
ROOT_URLCONF = 'config.urls'
TEMPLATES = [{
    'BACKEND': 'django.template.backends.django.DjangoTemplates',
    'DIRS': [], 'APP_DIRS': True,
    'OPTIONS': {'context_processors': [
        'django.template.context_processors.request',
        'django.contrib.auth.context_processors.auth',
        'django.contrib.messages.context_processors.messages',
    ]},
}]
WSGI_APPLICATION = 'config.wsgi.application'
AUTH_USER_MODEL = 'core.User'
database_url = os.environ.get('DATABASE_URL')
if database_url:
    parsed = urlparse(database_url)
    DATABASES = {'default': {
        'ENGINE': 'django.db.backends.postgresql', 'NAME': parsed.path.lstrip('/'),
        'USER': parsed.username, 'PASSWORD': parsed.password,
        'HOST': parsed.hostname, 'PORT': parsed.port or 5432,
    }}
else:
    DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': BASE_DIR / 'db.sqlite3'}}
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
STATIC_URL = 'static/'
MEDIA_ROOT = BASE_DIR / 'private_media'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'
if not DEBUG and 'test' not in sys.argv:
    SECURE_SSL_REDIRECT = os.environ.get('DJANGO_SECURE_SSL_REDIRECT', '1') == '1'
    SECURE_HSTS_SECONDS = int(os.environ.get('DJANGO_SECURE_HSTS_SECONDS', '31536000'))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

CACHES = {
    'default': {
        'BACKEND': os.environ.get(
            'DJANGO_CACHE_BACKEND',
            'django.core.cache.backends.locmem.LocMemCache',
        ),
        'LOCATION': os.environ.get('DJANGO_CACHE_LOCATION', 'mealsense-default-cache'),
    }
}

# Switch via env: AI_PROVIDER='' (off) | 'local' | 'dinov3' | 'dinov3_vlm' | 'openai' | 'gemini'.
_raw_ai_provider = '' if 'test' in sys.argv else os.environ.get('AI_PROVIDER', 'dinov3')
AI_PROVIDER = _raw_ai_provider.strip().lower()
AI_VISION_MODEL = os.environ.get('AI_VISION_MODEL', '').strip()
AI_API_KEYS = {
    'openai': os.environ.get('OPENAI_API_KEY', ''),
    'gemini': os.environ.get('GEMINI_API_KEY', ''),
}
AI_TIMEOUT_SECONDS = float(os.environ.get('AI_TIMEOUT_SECONDS', '30'))
AI_LOCAL_CHECKPOINT = os.environ.get(
    'AI_LOCAL_CHECKPOINT', str(BASE_DIR / 'model_artifacts/banglafoodnet/banglafoodnet_finetuned.pth'))
# CPU works without CUDA; use 'cuda' only with a compatible PyTorch installation.
AI_LOCAL_DEVICE = os.environ.get('AI_LOCAL_DEVICE', 'cpu').strip()
AI_DINOV3_MODEL_DIR = os.environ.get('AI_DINOV3_MODEL_DIR', str(BASE_DIR / 'ml_models/dinov3'))
AI_DINOV3_DEVICE = os.environ.get('AI_DINOV3_DEVICE', 'auto').strip().lower()
AI_DINOV3_TOP_K = int(os.environ.get('AI_DINOV3_TOP_K', '5'))
AI_VLM_CHECKPOINT = os.environ.get('AI_VLM_CHECKPOINT', 'mealsense-vlm-lora').strip()
AI_VLM_DEVICE = os.environ.get('AI_VLM_DEVICE', 'auto').strip().lower()
AI_VLM_ENABLED = os.environ.get('AI_VLM_ENABLED', '0').strip().lower() in ('1', 'true', 'yes')
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': ['rest_framework.authentication.SessionAuthentication'],
    'DEFAULT_PERMISSION_CLASSES': ['rest_framework.permissions.IsAuthenticated'],
    'DEFAULT_THROTTLE_CLASSES': ['rest_framework.throttling.AnonRateThrottle', 'rest_framework.throttling.UserRateThrottle'],
    'DEFAULT_THROTTLE_RATES': {'anon': '30/hour', 'user': '300/hour',
                               # Public doctor portal scopes replace the tight
                               # default anon limit on their own endpoints.
                               'doctor_request': '20/hour', 'doctor_view': '120/hour'},
}
