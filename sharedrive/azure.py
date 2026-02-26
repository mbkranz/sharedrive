from __future__ import annotations

import os

from dotenv import load_dotenv
from pydantic import BaseModel, Field, SecretStr, field_validator

from sharedrive.sharepoint import SharepointClient

load_dotenv()


class SpoConfig(BaseModel):
    tenant_id: str = Field(default=os.getenv("AZURE_TENANT_ID"))
    client_id: str = Field(default=os.getenv("AZURE_CLIENT_ID"))
    client_secret: SecretStr | None = Field(default=os.getenv("AZURE_CLIENT_SECRET"))
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
