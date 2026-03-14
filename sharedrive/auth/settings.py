from __future__ import annotations

from enum import Enum
from pathlib import Path

from dotenv import find_dotenv
from pydantic import AliasChoices, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from sharedrive.auth.base import CredentialStrategy
from sharedrive.auth.google import (
    DEFAULT_DRIVE_SCOPES,
    AdcStrategy,
    ServiceAccountStrategy,
    UserOAuthStrategy,
)
from sharedrive.auth.token_store import JsonTokenStore


class GoogleAuthMode(str, Enum):
    ADC = "adc"
    SERVICE_ACCOUNT = "service_account"
    USER_OAUTH = "user_oauth"


class GoogleAuthConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=find_dotenv(".env", usecwd=True),
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    auth_mode: GoogleAuthMode = Field(
        default=GoogleAuthMode.ADC,
        alias="GOOGLE_AUTH_MODE",
    )
    service_account_credentials: Path | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "GOOGLE_SERVICE_ACCOUNT_CREDENTIALS",
            "GOOGLE_APPLICATION_CREDENTIALS",
        ),
    )
    oauth_client_secrets: Path | None = Field(
        default=None,
        alias="GOOGLE_OAUTH_CREDENTIALS",
    )
    oauth_token_path: Path | None = Field(
        default=None,
        alias="GOOGLE_OAUTH_TOKEN_PATH",
    )
    scopes: list[str] = Field(
        default_factory=lambda: list(DEFAULT_DRIVE_SCOPES),
        alias="GOOGLE_SCOPES",
    )
    use_local_server: bool = Field(
        default=True,
        alias="GOOGLE_OAUTH_USE_LOCAL_SERVER",
    )

    @field_validator("scopes", mode="before")
    @classmethod
    def to_scope_list(cls, value: str | list[str] | tuple[str, ...] | None) -> list[str]:
        if value is None:
            return list(DEFAULT_DRIVE_SCOPES)
        if isinstance(value, str):
            parts = [part.strip() for part in value.split(",")]
            return [part for part in parts if part] or list(DEFAULT_DRIVE_SCOPES)
        return [scope for scope in value if scope]

    @model_validator(mode="after")
    def validate_for_mode(self) -> GoogleAuthConfig:
        if (
            self.auth_mode == GoogleAuthMode.SERVICE_ACCOUNT
            and self.service_account_credentials is None
        ):
            raise ValueError(
                "GOOGLE_APPLICATION_CREDENTIALS or GOOGLE_SERVICE_ACCOUNT_CREDENTIALS is required for service_account mode."
            )

        if (
            self.auth_mode == GoogleAuthMode.USER_OAUTH
            and self.oauth_client_secrets is None
        ):
            raise ValueError(
                "GOOGLE_OAUTH_CREDENTIALS is required for user_oauth mode."
            )

        return self

    def to_strategy(self) -> CredentialStrategy:
        if self.auth_mode == GoogleAuthMode.ADC:
            return AdcStrategy(scopes=self.scopes)

        if self.auth_mode == GoogleAuthMode.SERVICE_ACCOUNT:
            return ServiceAccountStrategy(
                credentials_path=self.service_account_credentials,
                scopes=self.scopes,
            )

        token_store = (
            JsonTokenStore(self.oauth_token_path)
            if self.oauth_token_path is not None
            else None
        )
        return UserOAuthStrategy(
            client_secrets_path=self.oauth_client_secrets,
            scopes=self.scopes,
            token_store=token_store,
            use_local_server=self.use_local_server,
        )


def make_google_drive_client_from_settings(
    config: GoogleAuthConfig | None = None,
):
    from sharedrive.clients.google import GoogleDriveClient

    resolved_config = config or GoogleAuthConfig()
    return GoogleDriveClient(credential_strategy=resolved_config.to_strategy())
