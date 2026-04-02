from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Iterable, cast

from sharedrive.models import DrivePackage, DriveResource


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
    def to_dp(self) -> DriveResource | DrivePackage:
        raise NotImplementedError


class DriveFile(DriveItem, ABC):
    @property
    def is_directory(self) -> bool:
        return False

    def to_dp(self) -> DriveResource:
        format_str = None
        if "." in self.name:
            format_str = self.name.rsplit(".", 1)[-1].lower()

        return DriveResource.from_drive_metadata(
            name=self.path,
            path=self.path,
            service_type=self.service_type,
            entity_type="File",
            source_url=self.source_url,
            format_str=format_str,
            drive_id=self.id,
        )

    def refresh(self, *, include_children: bool = True) -> "DriveFile":
        return self


class DriveFolder(DriveItem, ABC):
    @property
    def is_directory(self) -> bool:
        return True

    @property
    @abstractmethod
    def children(self) -> list[DriveItem]:
        raise NotImplementedError

    def iter_files(self) -> Iterable[DriveFile]:
        for child in self.children:
            if child.is_directory:
                yield from cast("DriveFolder", child).iter_files()
                continue
            yield cast(DriveFile, child)

    def download(self, target: Path | str) -> None:
        target_root = Path(target)
        target_root.mkdir(parents=True, exist_ok=True)
        for child in self.iter_files():
            child.download(target_root / Path(child.path))

    def to_dp(self) -> DrivePackage:
        return DrivePackage(
            name=self.path,
            path=self.path,
            driveId=self.id,
            sources=[
                {
                    "path": self.source_url,
                    "serviceType": self.service_type,
                    "entityType": "Directory",
                }
            ],
            resources=[child.to_dp() for child in self.children],
        )


__all__ = ["DriveFile", "DriveFolder", "DriveItem"]
