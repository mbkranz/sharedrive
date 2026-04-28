from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from sharedrive.models import DrivePackage, DriveResource,DriveCatalog


class DriveItem(ABC):
    @property
    @abstractmethod
    def id(self) -> str:
        raise NotImplementedError

    @property
    @abstractmethod
    def name(self) -> str:
        raise NotImplementedError

    @property
    @abstractmethod
    def path(self) -> str:
        raise NotImplementedError

    @property
    @abstractmethod
    def service_type(self) -> str:
        raise NotImplementedError

    @property
    @abstractmethod
    def source_url(self) -> str:
        raise NotImplementedError

    @property
    @abstractmethod
    def is_directory(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def download(self, target: Path | str) -> None:
        raise NotImplementedError

    @abstractmethod
    def refresh(self, *, include_children: bool = True) -> "DriveItem":
        """Refresh this runtime item from its backing service."""
        raise NotImplementedError

    @abstractmethod
    def to_dp(self) -> DriveResource | DrivePackage |DriveCatalog:
        # DriveResource.from_drive_metadata(
        #             name=self.path,
        #             path=self.path,
        #             service_type=self.service_type,
        #             entity_type="File",
        #             source_url=self.source_url,
        #             format_str=format_str,
        #             drive_id=self.id,
        #         )

        raise NotImplementedError
