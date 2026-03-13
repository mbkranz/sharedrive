from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Protocol, runtime_checkable

from google.auth.credentials import Credentials


class CredentialStrategy(ABC):
    @abstractmethod
    def build(self) -> Credentials:
        """Construct and return Google credentials."""


@runtime_checkable
class TokenStore(Protocol):
    def load(self) -> Credentials | None:
        ...

    def save(self, creds: Credentials) -> None:
        ...
