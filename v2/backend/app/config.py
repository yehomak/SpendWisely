from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # LLM provider: groq | claude | openai | gemini
    llm_provider: str = "groq"
    llm_model: str = ""  # leave empty to use provider default

    anthropic_api_key: str = ""  # claude
    openai_api_key: str = ""  # openai / chatgpt
    google_api_key: str = ""  # gemini
    groq_api_key: str = ""  # groq (free tier)

    db_path: str = "./spendwisely.duckdb"
    owner_name: str = ""  # set in .env — used to detect own-account transfers

    gmail_client_id: str = ""  # Google OAuth2 client id
    gmail_client_secret: str = ""  # Google OAuth2 client secret
    gmail_redirect_uri: str = "http://localhost:8000/api/v1/gmail/callback"

    suggest_rate_limit: int = 5  # max AI suggest calls per IP per window
    suggest_rate_window: int = 600  # window in seconds (default: 10 min)

    # OTP confirmation for sensitive actions (e.g. delete all transactions)
    otp_email_to: str = "owner@spendwisely.local"  # where confirmation codes are sent
    otp_ttl_seconds: int = 600  # code lifetime (10 min)
    otp_max_attempts: int = 5  # wrong codes before the challenge locks
    otp_resend_cooldown_seconds: int = 30  # "Resend in Ns" countdown

    # SMTP — defaults target Mailpit (docker compose dev: host "mailpit")
    smtp_host: str = "localhost"
    smtp_port: int = 1025
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_starttls: bool = False
    smtp_from: str = "SpendWisely <no-reply@spendwisely.local>"

    class Config:
        env_file = ".env"


settings = Settings()
