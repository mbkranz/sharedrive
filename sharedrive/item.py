"""Backward-compatibility shim.

DriveFile, DriveFolder, and DriveItem have moved to
``sharedrive.clients.base``.  This module re-exports them so that existing
code and tests that import from ``sharedrive.item`` continue to work.
"""
from sharedrive.clients.base import DriveFile, DriveFolder, DriveItem

__all__ = ["DriveFile", "DriveFolder", "DriveItem"]
