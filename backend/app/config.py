from functools import lru_cache

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL


class Settings(BaseSettings):
    """Configuration loaded from environment variables or a local .env file."""

    model_config = SettingsConfigDict(
        env_file=(".env", "backend/.env"),
        env_file_encoding="utf-8",
        enable_decoding=False,
        extra="ignore",
    )

    app_name: str = "Classroom Quiz Platform API"
    app_env: str = "development"
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])

    # DATABASE_URL can override the individual MySQL fields (useful for tests/CI).
    database_url: str | None = None
    db_host: str = ""
    db_port: int = 3306
    db_database: str = ""
    db_username: str = ""
    db_password: SecretStr = SecretStr("")
    db_connect_timeout: int = 5

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: object) -> object:
        if isinstance(value, str) and not value.lstrip().startswith("["):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @property
    def sqlalchemy_url(self) -> str | URL:
        if self.database_url:
            return self.database_url
        missing = [
            name
            for name, value in {
                "DB_HOST": self.db_host,
                "DB_DATABASE": self.db_database,
                "DB_USERNAME": self.db_username,
            }.items()
            if not value
        ]
        if missing:
            raise ValueError(
                "Missing database configuration: " + ", ".join(missing)
            )
        return URL.create(
            drivername="mysql+pymysql",
            username=self.db_username,
            password=self.db_password.get_secret_value(),
            host=self.db_host,
            port=self.db_port,
            database=self.db_database,
            query={
                "charset": "utf8mb4",
                "connect_timeout": str(self.db_connect_timeout),
            },
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
