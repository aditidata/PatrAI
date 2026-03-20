"""
PatrAI configuration — all secrets read exclusively from environment variables.
Never hardcode credentials here.
"""
import os

# LLM
OPENAI_API_KEY: str = os.environ.get("OPENAI_API_KEY", "")
OLLAMA_BASE_URL: str = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")

# Google OAuth
GOOGLE_CLIENT_ID: str = os.environ.get("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET: str = os.environ.get("GOOGLE_CLIENT_SECRET", "")
GOOGLE_REDIRECT_URI: str = os.environ.get("GOOGLE_REDIRECT_URI", "")

# Email / IMAP / SMTP
ASSISTANT_EMAIL: str = os.environ.get("ASSISTANT_EMAIL", "")
ASSISTANT_EMAIL_PASSWORD: str = os.environ.get("ASSISTANT_EMAIL_PASSWORD", "")
IMAP_SERVER: str = os.environ.get("IMAP_SERVER", "imap.gmail.com")
SMTP_SERVER: str = os.environ.get("SMTP_SERVER", "smtp.gmail.com")

# Infrastructure
REDIS_URL: str = os.environ.get("REDIS_URL", "redis://localhost:6379")
DUCKLING_URL: str = os.environ.get("DUCKLING_URL", "http://localhost:8000")

# Security
ENCRYPTION_KEY: str = os.environ.get("ENCRYPTION_KEY", "")

# Database
DB_PATH: str = os.environ.get("DB_PATH", "patrai.db")
