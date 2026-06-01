from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Iterator, TypeVar, overload

from sharedrive.models import DriveRemoteCatalog,DriveRemoteResource,ServiceId,ServiceTypeValue

DefaultT = TypeVar("DefaultT")


class ServiceItem(ABC):
    """Abstract base for a single item (file or directory) on a remote drive.

    All file-vs-directory behaviour is dispatched on :attr:`is_directory`.
    Concrete subclasses implement the service-specific transport layer
    (``refresh``, ``download``) while shared traversal logic lives here.

    Design note: this single ABC replaces the previous three-level hierarchy
    ``ServiceItem → DriveFile/DriveFolder → G/SharepointFile/Folder``.  The
    old ``DriveFile`` and ``DriveFolder`` sub-ABCs are retained below as thin
    backward-compatible shells so that existing subclasses continue to work
    without modification.
    
    
    # TODO: in a v2, consider making this a first class pydantic model under a remote namespace and removing current remote driven fields.

    """
    def __repr__(self) -> str:
        
        path = getattr(self, "path", None)
        if path is not None:
            name = getattr(self, "name", None)
            source_url = getattr(self, "source_url", None)
            return (
                f"{type(self).__name__}("
                f"service_type={getattr(self, 'service_type', None)!r}, "
                f"path={path!r}, "
                f"name={name!r}, "
                f"source_url={source_url!r}), "
                f"id={getattr(self, 'id', None)!r}, "
            )
        return f"{type(self).__name__}()"

    @property
    @abstractmethod
    def id(self) -> ServiceId:
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
    def service_type(self) -> ServiceTypeValue:
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
    def refresh(self, *, include_children: bool = True) -> "ServiceItem":
        """Refresh this runtime item from its backing service."""
        raise NotImplementedError

    @classmethod
    @abstractmethod
    def from_path(cls, *args: Any, **kwargs: Any) -> "ServiceItem":
        """Resolve a provider-specific path locator into a runtime item."""
        raise NotImplementedError

    # ------------------------------------------------------------------
    # Concrete shared behaviour
    # ------------------------------------------------------------------

    @property
    @abstractmethod
    def children(self) -> list["ServiceItem"]:
        """Direct child items for directories; always empty for files.

        Concrete directory subclasses override this to return populated
        children.  The default returns an empty list so that file items
        never need to override it.
        """
        raise NotImplementedError


    @abstractmethod
    def move(self, new_parent_id: str) -> "ServiceItem":
        """Move this item to a new parent folder, returning the updated item."""
        raise NotImplementedError

    @abstractmethod
    def add_comment(self, body: str) -> "ServiceItem":
        """Post a comment on this item."""
        raise NotImplementedError

    @overload
    def get_path(self, relative_path: str | Path) -> "ServiceItem | None": ...

    @overload
    def get_path(
        self, relative_path: str | Path, default: DefaultT
    ) -> "ServiceItem | DefaultT": ...

    def get_path(
        self, relative_path: str | Path, default: DefaultT | None = None
    ) -> "ServiceItem | DefaultT | None":
        """Resolve a descendant item by traversing child names in *relative_path*.

        The input path is normalized to POSIX-style segments (``\\`` → ``/``) and
        ignores empty segments and ``.`` markers. Lookup uses a linear scan over
        each directory's direct children for each path part.
        """
        parts = [
            part
            for part in str(relative_path).replace("\\", "/").split("/")
            if part and part != "."
        ]
        current: ServiceItem = self
        for part in parts:
            next_item = next((child for child in current.children if child.name == part), None)
            if next_item is None:
                return default
            current = next_item
        return current

    def iter_files(
        self,
        prefix: str | Path | None = None,
        recursive: bool = True,
    ) -> Iterator["ServiceItem"]:
        """Yield file descendants under *prefix* or all files if *prefix* is empty."""

        if prefix is None:
            start = self
        else:
            start = self.get_path(prefix)
            if start is None:
                raise ValueError(f"Prefix {prefix} not found under {self.path}.")

        if not start.is_directory:
            
            raise ValueError(f"{start.path} is not a directory, cannot iterate files under it.")

        def walk(item: ServiceItem) -> Iterator["ServiceItem"]:
            for child in item.children:
                if child.is_directory:
                    if recursive:
                        yield from walk(child)
                else:
                    yield child

        yield from walk(start)

    def refresh_tree(self) -> "ServiceItem":
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

    def to_catalog(self) -> DriveRemoteCatalog | DriveRemoteResource:
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
            return DriveRemoteResource(
                name=self.path,
                path=self.source_url,
                cache=self.path,
                serviceId=self.id,
                serviceType=self.service_type,
                entityType="File",
                format=format_str,
                
            )
        resources: list[DriveRemoteResource] = []
        catalogs: list[DriveRemoteCatalog] = []
        for child in self.children:
            entry = child.to_catalog()
            if isinstance(entry, DriveRemoteCatalog):
                catalogs.append(entry)
            elif isinstance(entry, DriveRemoteResource):
                resources.append(entry)
        return DriveRemoteCatalog(
            name=self.path,
            accessUrl=self.source_url,
            serviceId=self.id,
            serviceType=self.service_type,
            entityType="Directory",
            resources=resources,
            catalogs=catalogs,
        )

class DriveFile(ServiceItem):
    """Backward-compatible file item base class."""

    @property
    def is_directory(self) -> bool:
        return False


class DriveFolder(ServiceItem):
    """Backward-compatible folder item base class."""

    @property
    def is_directory(self) -> bool:
        return True


__all__ = ["DriveFile", "DriveFolder", "ServiceItem"]
