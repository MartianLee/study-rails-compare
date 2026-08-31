import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SECRET_KEY = "benchmark-only-not-a-secret"
DEBUG = False
ALLOWED_HOSTS = ["*"]

INSTALLED_APPS = ["blog"]

# The middleware an API-only Django service actually runs. No sessions, no auth,
# no CSRF — those belong to an HTML app, and Rails' --api mode drops them too.
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.common.CommonMiddleware",
]

ROOT_URLCONF = "blogbench.urls"
WSGI_APPLICATION = "blogbench.wsgi.application"
TEMPLATES = []

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.mysql",
        "NAME": os.environ.get("DB_NAME", "blogbench"),
        "USER": os.environ.get("DB_USER", "bench"),
        "PASSWORD": os.environ.get("DB_PASSWORD", "bench"),
        "HOST": os.environ.get("DB_HOST", "mysql"),
        "PORT": "3306",
        # Django has no connection pool; a persistent connection per worker
        # thread is the idiomatic equivalent.
        "CONN_MAX_AGE": int(os.environ.get("DB_CONN_MAX_AGE", "600")),
        "CONN_HEALTH_CHECKS": False,
        "OPTIONS": {"charset": "utf8mb4"},
    }
}

USE_TZ = True
TIME_ZONE = "UTC"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "WARNING"},
}
