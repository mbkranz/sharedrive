from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Iterator

from sharedrive.models import DrivePackage, DriveResource, DriveCatalog


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

    def download(self, target: Path | str) -> None:
        raise NotImplementedError(
            f"{type(self).__name__} does not implement download()."
        )

    @abstractmethod
    def refresh(self, *, include_children: bool = True) -> "DriveItem":
        """Refresh this runtime item from its backing service."""
        raise NotImplementedError

    def to_dp(self) -> DriveResource | DrivePackage | DriveCatalog:
        raise NotImplementedError(
            f"{type(self).__name__} does not implement to_dp()."
        )


class DriveFile(DriveItem):
    """Concrete ``DriveItem`` for file objects (``is_directory`` is always ``False``)."""

    @property
    def is_directory(self) -> bool:
        return False

    def iter_files(self) -> Iterator["DriveFile"]:
        """Yield *self* — a single file has no children to recurse into."""
        yield self

    def to_dp(self) -> DriveResource | DrivePackage | DriveCatalog:
        """Convert to a :class:`~sharedrive.models.DriveResource` using item attributes.

        Subclasses may override for richer conversion (e.g. to preserve
        mime-type information from the backing API).
        """
        name = str(self.name or "")
        path_str = str(self.path or name)
        suffix = Path(path_str).suffix.lstrip(".") if path_str else ""
        return DriveResource.from_drive_metadata(
            name=name,
            path=path_str,
            service_type=str(self.service_type or ""),
            entity_type="File",
            source_url=str(self.source_url or ""),
            format_str=suffix or None,
        )


class DriveFolder(DriveItem):
    """Concrete ``DriveItem`` for folder/directory objects (``is_directory`` is always ``True``).

    Subclasses must implement :attr:`children`.  The default :meth:`iter_files`
    and :meth:`refresh_tree` implementations are provided here.
    """

    @property
    def is_directory(self) -> bool:
        return True

    @property
    @abstractmethod
    def children(self) -> list[DriveItem]:
        """Return the direct children of this folder."""
        raise NotImplementedError

    def iter_files(self) -> Iterator[DriveFile]:
        """Recursively yield all non-directory descendants."""
        for child in self.children:
            if isinstance(child, DriveFolder):
                yield from child.iter_files()
            else:
                yield child  # type: ignore[misc]

    def refresh_tree(self) -> "DriveFolder":
        """Refresh this folder and recursively all its descendants.

        Calls :meth:`refresh` (without re-fetching children) on *self* first,
        then depth-first on every descendant.  The returned object is *self*.
        """
        self.refresh(include_children=False)
        for child in self.children:
            if isinstance(child, DriveFolder):
                child.refresh_tree()
            else:
                child.refresh(include_children=False)
        return self


__all__ = ["DriveFile", "DriveFolder", "DriveItem"]
