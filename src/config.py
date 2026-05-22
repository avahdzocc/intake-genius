from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # Anthropic
    anthropic_api_key: str

    # Twilio
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_phone_number: str = ""

    # Google Calendar
    google_calendar_credentials_path: str = "./credentials/google_calendar.json"
    google_calendar_scopes: str = "https://www.googleapis.com/auth/calendar"

    # Asana
    asana_access_token: str = ""
    asana_workspace_gid: str = ""
    asana_project_gid: str = ""         # "New Intakes" project
    asana_managing_partner_gid: str = "" # GID of the managing partner user

    # Database
    database_url: str = "./intake_genius.db"

    # Firm
    firm_name: str = "Chen, Rivers & Associates"
    intake_email: str = "intake@yourfirm.com"
    managing_partner_email: str = ""    # For conflict escalation

    # Security
    allowed_origins: str = ""            # comma-separated; empty = dev defaults
    internal_api_key: str = ""           # protects /api/internal/* in prod

    # App
    base_url: str = "http://localhost:8000"
    business_hours_start: int = 9       # 9 AM local
    business_hours_end: int = 17        # 5 PM local
    consultation_duration_minutes: int = 60
    timezone: str = "America/Los_Angeles"
    follow_up_interval_seconds: int = 21600  # 6 hours between stale-case sweeps


settings = Settings()
