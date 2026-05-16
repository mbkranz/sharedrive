from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Iterable

from sharedrive.models import DriveCatalog, DrivePackage, DriveResource, DriveSource


class DriveItem(ABC):
    """Abstract base for a single item (file or directory) on a remote drive.

    All file-vs-directory behaviour is dispatched on :attr:`is_directory`.
    Concrete subclasses implement the service-specific transport layer
    (``refresh``, ``download``) while shared traversal logic lives here.

    Design note: this single ABC replaces the previous three-level hierarchy
    ``DriveItem → DriveFile/DriveFolder → G/SharepointFile/Folder``.  The
    old ``DriveFile`` and ``DriveFolder`` sub-ABCs are retained below as thin
    backward-compatible shells so that existing subclasses continue to work
    without modification.

    TODO: decide how to use DriveItem vs just using DriveSource <--> client methods
    """

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
    def refresh(self, *, include_children: bool = True) -> "DriveItem":
        """Refresh this runtime item from its backing service."""
        raise NotImplementedError

    # ------------------------------------------------------------------
    # Concrete shared behaviour
    # ------------------------------------------------------------------

    @property
    def children(self) -> list["DriveItem"]:
        """Direct child items for directories; always empty for files.

        Concrete directory subclasses override this to return populated
        children.  The default returns an empty list so that file items
        never need to override it.
        """
        return []

    def iter_files(self) -> Iterable["DriveItem"]:
        """Recursively yield all leaf (non-directory) items.

        For a file item, yields ``self``.  For a directory, recurses into
        :attr:`children`.
        """
        if not self.is_directory:
            yield self
            return
        for child in self.children:
            yield from child.iter_files()

    def refresh_tree(self) -> "DriveItem":
        """Recursively refresh this item and all of its descendants."""
        self.refresh(include_children=True)
        if self.is_directory:
            for child in self.children:
                child.refresh_tree()
        return self

    def download(self, target: Path | str) -> None:
        """Download this item to *target*.

        For directories, walks all leaf files via :meth:`iter_files` and
        writes each one relative to *target*.  For files, concrete
        subclasses must override this method; the default raises
        :exc:`NotImplementedError`.
        """
        if self.is_directory:
            target_root = Path(target)
            target_root.mkdir(parents=True, exist_ok=True)
            for child in self.iter_files():
                child.download(target_root / Path(child.path))
            return
        raise NotImplementedError(
            f"File download is not implemented for {type(self).__name__}. "
            "Concrete subclasses must override download()."
        )

    def to_source(self) -> DriveSource:
        """Convert to a provenance source entry."""
        return DriveSource(title=self.name, path=self.source_url)

    def to_resource(self) -> DriveResource | DrivePackage | DriveCatalog:
        """Convert to a descriptor resource, package, or catalog entry.

        - Files → :class:`~sharedrive.models.DriveResource` with the remote URL
          in ``path`` and the relative materialized path in ``_cache``.
        - Directories → :class:`~sharedrive.models.DriveCatalog` with the remote
          folder URL in ``accessURL``.
        """
        if not self.is_directory:
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
        resources: list[DriveResource] = []
        catalogs: list[DriveCatalog] = []
        for child in self.children:
            entry = child.to_resource()
            if isinstance(entry, DriveCatalog):
                catalogs.append(entry)
            elif isinstance(entry, DriveResource):
                resources.append(entry)
        return DriveCatalog(
            name=self.path,
            accessURL=self.source_url,
            serviceType=self.service_type,
            entityType="Directory",
            driveId=self.id,
            resources=resources,
            catalogs=catalogs,
        )

    def to_dp(self) -> DriveResource | DrivePackage:
        """Deprecated alias for :meth:`to_resource`.

        .. deprecated::
            Use :meth:`to_resource` instead.
        """
        return self.to_resource()


class DriveFile(DriveItem):
    """Backward-compatible file item base class."""

    @property
    def is_directory(self) -> bool:
        return False


class DriveFolder(DriveItem):
    """Backward-compatible folder item base class."""

    @property
    def is_directory(self) -> bool:
        return True


__all__ = ["DriveFile", "DriveFolder", "DriveItem"]
