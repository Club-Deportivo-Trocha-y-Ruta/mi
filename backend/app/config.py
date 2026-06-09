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

    # -----------------------------------------------------------------------
    # Race AI — budget guard (F8A)
    # -----------------------------------------------------------------------
    # Presupuesto mensual (USD) para todos los runs del módulo race-analyst.
    # Cuando la suma de cost_usd en los últimos 30 días lo excede, el
    # endpoint POST /api/race-analysis/runs responde 503 y se envía alerta
    # por email al coach + admin. Runs en curso completan.
    # Ver: app/services/race/ai/budget_guard.py + docs/10-race-results/runbook-ops.md
    race_ai_budget_usd_30d: float = 20.0

    # -----------------------------------------------------------------------
    # Media de sesiones (fotos/videos vía SFTP a Hostinger)
    # -----------------------------------------------------------------------
    # SFTP de destino (Hostinger web hosting). En tests/local queda vacío y
    # el storage backend usa un fallback local en static/uploads/media.
    hostinger_sftp_host: str = ""
    hostinger_sftp_port: int = 22
    hostinger_sftp_user: str = ""
    hostinger_sftp_pass: str = ""
    # Directorio absoluto remoto donde se escriben los archivos.
    hostinger_sftp_remote_dir: str = ""
    # Base URL pública desde donde se servirán las media (HTTPS).
    # Debe terminar SIN slash; el servicio agrega la ruta relativa.
    hostinger_public_base_url: str = ""

    # Límites
    media_max_photo_mb: int = 10
    media_max_video_mb: int = 120

    # -----------------------------------------------------------------------
    # Race results upload UI (F-UP* — docs/10-race-results/upload-design.md)
    # -----------------------------------------------------------------------
    # Tamaño máximo por PDF subido vía wizard upload (RESULTADOS o GENERAL).
    # PDFs Federación reales ≈ 250 KB; 8 MB deja 32x margen.
    race_max_pdf_mb: int = 8
    # Timeout asyncio.wait_for(...) alrededor de pdfplumber. Si un PDF requiere
    # más, se rechaza con HTTP 422 ("PDF demasiado complejo").
    race_parse_timeout_seconds: int = 30
    # TTL para RaceImport.status=pending creados por /parse pero nunca commited
    # (wizard abandonado). Cleanup nocturno descrito en upload-design.md §8.3.
    race_pending_ttl_hours: int = 24

    # -----------------------------------------------------------------------
    # Restablecimiento de contraseña (specs/003-password-reset-login)
    # -----------------------------------------------------------------------
    # Vigencia del enlace de restablecimiento. OWASP: rara vez > 1 hora.
    password_reset_token_ttl_minutes: int = 60
    # Máximo de solicitudes por correo dentro de la ventana (anti-flooding).
    password_reset_max_per_window: int = 3
    # Ventana móvil (minutos) para el conteo de rate-limit por correo.
    password_reset_window_minutes: int = 15

    # -----------------------------------------------------------------------
    # Cambio de correo del perfil (specs/004-user-profile)
    # -----------------------------------------------------------------------
    # Vigencia del enlace de confirmación enviado a la NUEVA dirección.
    email_change_token_ttl_minutes: int = 60
    # Máximo de solicitudes de cambio por usuario dentro de la ventana.
    email_change_max_per_window: int = 3
    # Ventana móvil (minutos) para el rate-limit de cambio de correo.
    email_change_window_minutes: int = 15

    @field_validator("hostinger_public_base_url")
    @classmethod
    def _strip_trailing_slash(cls, v: str) -> str:
        return v.rstrip("/")

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

    # MYSQL_ROOT_PASS lo consume docker-compose para inicializar el contenedor MySQL,
    # no Settings. extra="ignore" evita que pydantic falle por esa clave compartida.
    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


settings = Settings()
