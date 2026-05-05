from pydantic import field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # MySQL
    mysql_host: str = "localhost"
    mysql_port: int = 3306
    mysql_user: str = "trocha"
    mysql_pass: str = "changeme"
    mysql_db: str = "trocha_ruta"

    # JWT
    jwt_secret_key: str = "cambiar-en-produccion"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 30
    jwt_refresh_token_expire_days: int = 7

    # App
    app_env: str = "development"
    app_debug: bool = False
    cors_origins: str = "http://localhost:5173"

    # -----------------------------------------------------------------------
    # Email / Notificaciones
    # -----------------------------------------------------------------------
    # Proveedor: "smtp" (dev/MailHog) | "resend" (producción)
    email_provider: str = "smtp"

    # SMTP (MailHog en dev, relay real en staging)
    smtp_host: str = "mailhog"
    smtp_port: int = 1025
    smtp_user: str | None = None
    smtp_pass: str | None = None
    smtp_use_tls: bool = False
    smtp_start_tls: bool = False

    # Resend (producción) — nunca en repositorio
    resend_api_key: str = ""

    # Remitente
    email_from_address: str = "noreply@trochayruta.co"
    email_from_name: str = "Trocha y Ruta"

    # Nombre del club (para contexto de templates)
    club_name: str = "Club Deportivo Trocha y Ruta"

    # URL del frontend (para construir enlaces en emails)
    frontend_base_url: str = "http://localhost:5173"

    # Flags de control
    # False → cortocircuita sin enviar (CI, tests end-to-end)
    notification_send_emails: bool = True
    # True → loguea cuerpo del email (NUNCA activar en producción)
    notification_log_bodies: bool = False

    # -----------------------------------------------------------------------
    # IA / LLMs
    # -----------------------------------------------------------------------
    # False → la factoría devuelve FakeLLMProvider (sin red, sin API key).
    ai_enabled: bool = False
    # Proveedor: "anthropic" | "openai" | "google" | "fake".
    # Strategy + Factory: agregar uno nuevo no toca a los use cases.
    ai_provider: str = "anthropic"
    # ID de modelo del proveedor.
    ai_model: str = "claude-sonnet-4-5"
    # API key del proveedor — vacío en repo, validator exige valor en producción.
    ai_api_key: str = ""
    # Override opcional del endpoint (proxies, gateways corporativos).
    ai_base_url: str | None = None
    # Tope de tokens de salida — control de costos.
    ai_max_tokens: int = 1024
    # Timeout por request (segundos).
    ai_timeout_seconds: float = 30.0
    # Temperatura para generación.
    ai_temperature: float = 0.4
    # True → loguea prompts y respuestas (NUNCA activar en producción).
    ai_log_prompts: bool = False

    @field_validator("jwt_secret_key")
    @classmethod
    def validate_jwt_secret(cls, v: str, info) -> str:
        if v == "cambiar-en-produccion":
            import warnings
            warnings.warn(
                "JWT_SECRET_KEY usa valor por defecto. "
                "Generar con: python -c \"import secrets; print(secrets.token_hex(32))\"",
                stacklevel=2,
            )
        return v

    @field_validator("email_provider")
    @classmethod
    def validate_email_provider_in_prod(cls, v: str, info) -> str:
        env = info.data.get("app_env", "development")
        if env == "production" and v.lower() != "resend":
            raise ValueError(
                f"EMAIL_PROVIDER='{v}' inválido en producción. "
                "Debe ser 'resend' (SMTP/MailHog solo en dev)."
            )
        return v

    @field_validator("resend_api_key")
    @classmethod
    def validate_resend_key_in_prod(cls, v: str, info) -> str:
        env = info.data.get("app_env", "development")
        provider = info.data.get("email_provider", "smtp").lower()
        if env == "production" and provider == "resend" and not v:
            raise ValueError(
                "RESEND_API_KEY requerida cuando EMAIL_PROVIDER=resend en producción."
            )
        return v

    @field_validator("ai_provider")
    @classmethod
    def validate_ai_provider(cls, v: str, info) -> str:
        allowed = {"anthropic", "openai", "google", "fake"}
        normalized = v.lower().strip()
        if normalized not in allowed:
            raise ValueError(
                f"AI_PROVIDER='{v}' inválido. Permitidos: {sorted(allowed)}."
            )
        return normalized

    @field_validator("ai_api_key")
    @classmethod
    def validate_ai_api_key_in_prod(cls, v: str, info) -> str:
        env = info.data.get("app_env", "development")
        enabled = info.data.get("ai_enabled", False)
        provider = info.data.get("ai_provider", "anthropic")
        if env == "production" and enabled and provider != "fake" and not v:
            raise ValueError(
                "AI_API_KEY requerida cuando AI_ENABLED=true en producción "
                f"(AI_PROVIDER={provider})."
            )
        return v

    @field_validator("ai_log_prompts")
    @classmethod
    def forbid_ai_log_prompts_in_prod(cls, v: bool, info) -> bool:
        env = info.data.get("app_env", "development")
        if env == "production" and v:
            raise ValueError(
                "AI_LOG_PROMPTS=true PROHIBIDO en producción "
                "(privacidad de menores)."
            )
        return v

    @property
    def database_url(self) -> str:
        return (
            f"mysql+aiomysql://{self.mysql_user}:{self.mysql_pass}"
            f"@{self.mysql_host}:{self.mysql_port}/{self.mysql_db}"
        )

    @property
    def database_url_sync(self) -> str:
        return (
            f"mysql+pymysql://{self.mysql_user}:{self.mysql_pass}"
            f"@{self.mysql_host}:{self.mysql_port}/{self.mysql_db}"
        )

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
