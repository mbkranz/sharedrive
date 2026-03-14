from __future__ import annotations

from dotenv import find_dotenv
from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from sharedrive.sharepoint import SharepointClient


class SpoConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=find_dotenv(usecwd=True),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    tenant_id: str = Field(alias="AZURE_TENANT_ID", default="")
    client_id: str = Field(alias="AZURE_CLIENT_ID", default="")
    client_secret: SecretStr | None = Field(
        alias="AZURE_CLIENT_SECRET", default=None, validate_default=True
    )
    scope: list[str] = Field(default=["https://graph.microsoft.com/.default"])
    user_delegated_access: bool = Field(default=True)
    host_url: str = Field(default="")

    @field_validator("scope", mode="before")
    @classmethod
    def to_list(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, str):
            return [value]
        return value

    def to_client(self) -> SharepointClient:
        return SharepointClient(
            tenant_id=self.tenant_id,
            client_id=self.client_id,
            client_secret=self.client_secret.get_secret_value() if self.client_secret else None,
            host_url=self.host_url,
            scope=self.scope,
            user_delegated_access=self.user_delegated_access,
        )
