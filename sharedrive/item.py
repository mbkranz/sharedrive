"""Backward-compatible re-export shim.

``DriveItem``, ``DriveFile``, and ``DriveFolder`` now live in
:mod:`sharedrive.clients.base`.  This module exists solely to preserve
existing import paths::

    from sharedrive.item import DriveFile, DriveFolder, DriveItem  # still works
"""

from sharedrive.clients.base import DriveFile, DriveFolder, DriveItem

__all__ = ["DriveFile", "DriveFolder", "DriveItem"]
