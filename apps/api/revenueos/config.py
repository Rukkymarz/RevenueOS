from dataclasses import dataclass
import os
from urllib.parse import urlsplit


def required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is not configured")
    return value


@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv("DATABASE_URL", "postgresql+psycopg://revenueos:revenueos@localhost:5432/revenueos")
    oidc_issuer: str = os.getenv("OIDC_ISSUER", "http://localhost:8080/realms/revenueos")
    oidc_jwks_url: str = os.getenv("OIDC_JWKS_URL", "http://localhost:8080/realms/revenueos/protocol/openid-connect/certs")
    oidc_audience: str = os.getenv("OIDC_AUDIENCE", "revenueos-api")
    bootstrap_admin_email: str = os.getenv("BOOTSTRAP_ADMIN_EMAIL", "").strip().lower()
    cors_origins: tuple[str, ...] = tuple(filter(None, os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")))
    resend_api_key: str = os.getenv("RESEND_API_KEY", "")
    resend_from: str = os.getenv("RESEND_FROM", "")
    media_dir: str = os.getenv("MEDIA_DIR", "/data/media")
    ai_timeout_seconds: int = int(os.getenv("AI_TIMEOUT_SECONDS", "25"))
    ai_max_output_tokens: int = min(4096, int(os.getenv("AI_MAX_OUTPUT_TOKENS", "700")))
    ai_daily_run_limit: int = int(os.getenv("AI_DAILY_RUN_LIMIT", "30"))
    ai_enabled: bool = os.getenv("AI_ENABLED", "false").lower() == "true"
    metrics_token: str = os.getenv("METRICS_TOKEN", "")
    app_env: str = os.getenv("APP_ENV", "development").lower()
    public_base_url: str = os.getenv("PUBLIC_BASE_URL", "")
    unsubscribe_secret: str = os.getenv("UNSUBSCRIBE_SECRET", "")
    outreach_postal_address: str = os.getenv("OUTREACH_POSTAL_ADDRESS", "")
    redis_url: str = os.getenv("REDIS_URL", "")
    public_site_audits: bool = os.getenv("ENABLE_PUBLIC_SITE_AUDITS", "false").lower() == "true"
    trust_proxy_headers: bool = os.getenv("TRUST_PROXY_HEADERS", "false").lower() == "true"


def validate_production(settings: Settings) -> None:
    if settings.app_env != "production":
        return
    errors: list[str] = []
    from sqlalchemy.engine import make_url
    try:
        database = make_url(settings.database_url)
        if database.get_backend_name() != "postgresql" or database.username != "revenueos_app":
            errors.append("DATABASE_URL must use PostgreSQL with the non-owner revenueos_app role")
        if not database.password or len(database.password) < 24:
            errors.append("DATABASE_URL requires a strong runtime database password")
    except Exception:
        errors.append("DATABASE_URL is invalid")
    if urlsplit(settings.oidc_issuer).scheme != "https":
        errors.append("OIDC_ISSUER must use HTTPS")
    if urlsplit(settings.public_base_url).scheme != "https":
        errors.append("PUBLIC_BASE_URL must use HTTPS")
    if not settings.bootstrap_admin_email or "@" not in settings.bootstrap_admin_email:
        errors.append("BOOTSTRAP_ADMIN_EMAIL is required")
    if not settings.cors_origins or any(urlsplit(origin).scheme != "https" for origin in settings.cors_origins):
        errors.append("CORS_ORIGINS must contain only HTTPS origins")
    if len(settings.metrics_token) < 32:
        errors.append("METRICS_TOKEN must have at least 32 characters")
    if settings.resend_api_key and not (settings.resend_from and len(settings.unsubscribe_secret) >= 32 and settings.outreach_postal_address):
        errors.append("Email requires RESEND_FROM, UNSUBSCRIBE_SECRET and OUTREACH_POSTAL_ADDRESS")
    if not settings.redis_url.startswith("redis://") and not settings.redis_url.startswith("rediss://"):
        errors.append("REDIS_URL required for distributed production rate limits")
    if settings.ai_daily_run_limit < 1 or settings.ai_daily_run_limit > 1000:
        errors.append("AI_DAILY_RUN_LIMIT must be between 1 and 1000")
    if errors:
        raise RuntimeError("Unsafe production configuration: " + "; ".join(errors))

settings = Settings()
validate_production(settings)
