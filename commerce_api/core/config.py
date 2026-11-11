from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", populate_by_name=True
    )

    app_env: str = "development"
    database_url: str = Field(
        default="postgresql+asyncpg://commerce_runtime:runtime_dev_only@localhost:5432/commerce",
        validation_alias="COMMERCE_DATABASE_URL",
    )
    migration_database_url: str | None = None
    jwt_secret_key: SecretStr = Field(min_length=32)
    digital_asset_encryption_key: SecretStr | None = None
    access_token_minutes: int = Field(default=15, ge=1, le=60)
    refresh_token_days: int = Field(default=30, ge=1, le=365)

    @model_validator(mode="after")
    def reject_example_secret_in_production(self):
        if self.app_env == "production" and self.jwt_secret_key.get_secret_value().startswith("CHANGE_ME_"):
            raise ValueError("JWT_SECRET_KEY must be replaced before production startup")
        return self