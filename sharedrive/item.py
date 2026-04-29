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
        """Convert to a :class:`~sharedrive.models.DriveSource` remote pointer.

        Returns the minimal remote-pointer form of this item: just the URL,
        service type, and entity type.  Use this when you only need to record
        *where* this item lives, without the full descriptor metadata (name,
        path, format, driveId, …) that :meth:`to_resource` produces.
        """
        entity_type = "Directory" if self.is_directory else "File"
        return DriveSource(
            path=self.source_url,
            serviceType=self.service_type,
            entityType=entity_type,
        )

    def to_resource(self) -> DriveResource | DrivePackage | DriveCatalog:
        """Convert to a descriptor resource, package, or catalog entry.

        - Files → :class:`~sharedrive.models.DriveResource` (leaf entry with
          name, path, format, driveId, and a :class:`~sharedrive.models.DriveSource`
          pointing back to the remote item).
        - Directories → :class:`~sharedrive.models.DrivePackage` with a
          ``sources`` list and a nested ``resources`` list built from direct
          children.  The return type union includes
          :class:`~sharedrive.models.DriveCatalog` to accommodate subclasses or
          future service adapters that override this method to produce a catalog
          entry instead.
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
            resources=[child.to_resource() for child in self.children],
        )

    def to_dp(self) -> DriveResource | DrivePackage:
        """Deprecated alias for :meth:`to_resource`.

        .. deprecated::
            Use :meth:`to_resource` instead.
        """
        return self.to_resource()


class DriveFile(DriveItem, ABC):
    """Backward-compatible shell for a leaf (non-directory) drive item.

    .. deprecated::
        Subclass :class:`DriveItem` directly and implement ``is_directory``
        returning ``False``.  ``DriveFile`` will be removed in a future release.

    New code should subclass :class:`DriveItem` directly and provide a
    concrete ``is_directory`` property returning ``False``.
    """

    def __init_subclass__(cls, **kwargs: object) -> None:
        import warnings

        super().__init_subclass__(**kwargs)
        warnings.warn(
            f"{cls.__name__} subclasses DriveFile which is deprecated. "
            "Inherit from DriveItem directly instead.",
            DeprecationWarning,
            stacklevel=2,
        )

    @property
    def is_directory(self) -> bool:
        return False


class DriveFolder(DriveItem, ABC):
    """Backward-compatible shell for a directory drive item.

    .. deprecated::
        Subclass :class:`DriveItem` directly and implement ``is_directory``
        returning ``True``.  ``DriveFolder`` will be removed in a future release.

    New code should subclass :class:`DriveItem` directly and provide a
    concrete ``is_directory`` property returning ``True``.
    """

    def __init_subclass__(cls, **kwargs: object) -> None:
        import warnings

        super().__init_subclass__(**kwargs)
        warnings.warn(
            f"{cls.__name__} subclasses DriveFolder which is deprecated. "
            "Inherit from DriveItem directly instead.",
            DeprecationWarning,
            stacklevel=2,
        )

    @property
    def is_directory(self) -> bool:
        return True

    @property
    @abstractmethod
    def children(self) -> list[DriveItem]:
        raise NotImplementedError


__all__ = ["DriveItem"]
