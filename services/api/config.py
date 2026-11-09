import hashlib
import re
from functools import lru_cache
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')
    app_env: str = 'production'
    database_url: str = 'sqlite:///./linguaquest.db'
    bot_token: str = ''
    bot_username: str = ''
    webhook_secret: str = ''
    webapp_url: str = 'http://localhost:5173'
    admin_telegram_ids: str = ''
    ai_api_key: str = ''
    ai_model: str = 'gpt-4.1-mini'
    ai_enabled: bool = False
    ai_daily_token_budget: int = 100000
    ai_input_usd_per_million: float = 0.4
    ai_output_usd_per_million: float = 1.6
    enable_dev_auth: bool = False
    support_contact: str = ''
    commerce_enabled: bool = False

    @field_validator('database_url', mode='before')
    @classmethod
    def postgres_driver(cls, value):
        # PaaS connection strings omit the installed psycopg v3 driver name.
        if isinstance(value, str):
            for prefix in ('postgres://', 'postgresql://'):
                if value.startswith(prefix):
                    return 'postgresql+psycopg://' + value[len(prefix):]
        return value

    @field_validator('webhook_secret', mode='before')
    @classmethod
    def telegram_webhook_secret(cls, value):
        # Render-generated values can be base64. Telegram accepts only A-Z/a-z/0-9/_/-
        # and at most 256 characters. Sender and webhook receiver share this setting.
        # Do not expand short inputs: startup must still reject weak secrets.
        if isinstance(value, str) and len(value) >= 32:
            if len(value) > 256 or re.fullmatch(r'[A-Za-z0-9_-]+', value) is None:
                return hashlib.sha256(value.encode('utf-8')).hexdigest()
        return value

    @property
    def production(self):
        return self.app_env == 'production'

    @property
    def admins(self):
        return {int(x) for x in self.admin_telegram_ids.split(',') if x.strip()}

@lru_cache
def settings():
    return Settings()
