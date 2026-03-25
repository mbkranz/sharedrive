from abc import ABC, abstractmethod
from typing import Optional
import pathlib

from sharedrive.models import DriveResource


class DriveItem(ABC):
    """
    Active Path-like entity representing a target file or folder on a remote drive.
    Unlike passive metadata schemas, this acts as the interface to the literal binary bytes.
    """

    @property
    @abstractmethod
    def id(self) -> str:
        """The native drive ID for the item."""
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """The file or folder native name."""
        pass
    
    @property
    @abstractmethod
    def path(self) -> str:
        """
        The relative path of this item in the sync scope constraint. 
        Usually aligns with descriptor "name" or path.
        """
        pass

    @property
    @abstractmethod
    def is_directory(self) -> bool:
        """Whether this item is a folder container."""
        pass

    @property
    @abstractmethod
    def service_type(self) -> str:
        """String constant for this drive adapter (e.g. 'GoogleDrive', 'SharePoint')"""
        pass

    @property
    @abstractmethod
    def source_url(self) -> str:
        """The specific canonical URL mapping to this item (e.g. download or open link)"""
        pass

    @abstractmethod
    def download(self, target_dir: pathlib.Path | str) -> None:
        """
        Pull the file bytes down to the target tree context.
        Should raise a NotImplementedError if `is_directory` is True.
        """
        pass

    def to_dp(self) -> DriveResource:
        """
        Convert this active item instance into a passive Data Package Resource state block.
        """
        format_str = None
        if "." in self.name and not self.is_directory:
            format_str = self.name.split(".")[-1]

        type_str = "table" if format_str in ("csv", "xls", "xlsx") else "file"

        return DriveResource.from_drive_metadata(
            name=self.path,
            path=self.path,
            service_type=self.service_type,
            entity_type="Directory" if self.is_directory else "File",
            source_url=self.source_url,
            type_str=type_str,
            format_str=format_str,
            drive_id=self.id,
        )


__all__ = ["DriveItem"]
