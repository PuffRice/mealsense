import os
from pathlib import Path
from urllib.parse import urlparse
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / '.env', override=False)
SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', 'dev-only-change-me-before-deploying')
DEBUG = os.environ.get('DJANGO_DEBUG', '1') == '1'
if not DEBUG and SECRET_KEY == 'dev-only-change-me-before-deploying':
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
# Switch via env: AI_PROVIDER='' (off) | 'local' | 'openai' | 'gemini'.
AI_PROVIDER = os.environ.get('AI_PROVIDER', '').strip().lower()
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
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': ['rest_framework.authentication.SessionAuthentication'],
    'DEFAULT_PERMISSION_CLASSES': ['rest_framework.permissions.IsAuthenticated'],
    'DEFAULT_THROTTLE_CLASSES': ['rest_framework.throttling.AnonRateThrottle', 'rest_framework.throttling.UserRateThrottle'],
    'DEFAULT_THROTTLE_RATES': {'anon': '30/hour', 'user': '300/hour',
                               # Public doctor portal scopes replace the tight
                               # default anon limit on their own endpoints.
                               'doctor_request': '20/hour', 'doctor_view': '1200/hour'},
}
