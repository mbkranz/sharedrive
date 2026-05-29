from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import boto3
from botocore.exceptions import ClientError

from sharedrive.clients.base import AdapterCapabilities, BaseClient
from sharedrive.item import ServiceItem
from sharedrive.registry import provider


def check_s3_credentials() -> None:
    """Validate that AWS credentials are available for S3 operations."""
    session = boto3.Session()
    credentials = session.get_credentials()
    if credentials is None:
        raise RuntimeError(
            "No AWS credentials were found in the current environment or configuration."
        )

    frozen = credentials.get_frozen_credentials()
    if not frozen.access_key or not frozen.secret_key:
        raise RuntimeError("AWS credentials are incomplete for S3 operations.")


def _parse_s3_source_url(
    source_url: str, *, allow_empty_key: bool = False
) -> tuple[str, str]:
    """Parse an S3 URL into bucket/key.

    Returns ``(bucket, key)`` where ``bucket`` is the S3 bucket name and ``key``
    is the object key or prefix (possibly empty when ``allow_empty_key`` is set).
    Set ``allow_empty_key=True`` for bucket-root directory locators.
    """
    parsed = urlparse(source_url)
    scheme = parsed.scheme.lower()

    if scheme == "s3":
        bucket = parsed.netloc
        key = parsed.path.lstrip("/")
    elif scheme in {"http", "https"}:
        host = parsed.netloc.lower()
        path = parsed.path.lstrip("/")
        if host == "s3.amazonaws.com" or host.startswith("s3."):
            parts = path.split("/", 1)
            bucket = parts[0] if parts else ""
            key = parts[1] if len(parts) > 1 else ""
        elif ".s3." in host or host.endswith(".s3.amazonaws.com"):
            bucket = host.split(".s3", 1)[0]
            key = path
        else:
            raise ValueError(f"Unsupported S3 URL host: {parsed.netloc}")
    else:
        raise ValueError(f"Unsupported URL scheme for S3 source: {parsed.scheme}")

    if not bucket:
        raise ValueError(f"Could not parse bucket from source URL: {source_url}")
    if not allow_empty_key and not key:
        raise ValueError(f"Could not parse key from source URL: {source_url}")
    return bucket, key


@provider("s3")
class S3Client(BaseClient):
    auth_methods = ["aws_credentials"]
    capabilities = AdapterCapabilities(
        supports_fetch=True,
        supports_download=True,
        supports_auth_check=True,
        supports_write=False,
    )

    def __init__(self, *, client: Any = None) -> None:
        self.client = client or boto3.client("s3")

    @classmethod
    def build_default(cls) -> "S3Client":
        check_s3_credentials()
        return cls()

    @classmethod
    def check_auth(cls) -> None:
        check_s3_credentials()

    def get_from_weburl(self, url: str) -> "S3Item":
        bucket, key = _parse_s3_source_url(url, allow_empty_key=True)
        if not key or key.endswith("/"):
            return S3Item(client=self, bucket=bucket, key=key, is_directory=True)

        try:
            self.client.head_object(Bucket=bucket, Key=key)
            return S3Item(client=self, bucket=bucket, key=key, is_directory=False)
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            if code in {"404", "NotFound", "NoSuchKey"}:
                prefix = key if key.endswith("/") else f"{key}/"
                response = self.client.list_objects_v2(
                    Bucket=bucket,
                    Prefix=prefix,
                    MaxKeys=1,
                )
                if response.get("KeyCount", 0) > 0:
                    return S3Item(
                        client=self, bucket=bucket, key=prefix, is_directory=True
                    )
            raise


class S3Item(ServiceItem):
    def __init__(
        self,
        *,
        client: S3Client,
        bucket: str,
        key: str,
        is_directory: bool,
        children: list["S3Item"] | None = None,
    ) -> None:
        self.client = client
        self.bucket = bucket
        self.key = key
        self._is_directory = is_directory
        self._children = children

    @property
    def id(self) -> str:
        return f"{self.bucket}:{self.key}"

    @property
    def name(self) -> str:
        cleaned = self.key.rstrip("/")
        if not cleaned:
            return self.bucket
        return Path(cleaned).name

    @property
    def path(self) -> str:
        return self.key

    @property
    def service_type(self) -> str:
        return "S3"

    @property
    def source_url(self) -> str:
        return f"s3://{self.bucket}/{self.key}" if self.key else f"s3://{self.bucket}"

    @property
    def is_directory(self) -> bool:
        return self._is_directory

    @property
    def children(self) -> list["S3Item"]:
        if not self.is_directory:
            return []
        if self._children is None:
            self.refresh(include_children=True)
        return self._children or []

    def refresh(self, *, include_children: bool = True) -> "S3Item":
        if not self.is_directory:
            return self
        if not include_children:
            return self

        prefix = self.key if self.key.endswith("/") or not self.key else f"{self.key}/"
        response = self.client.client.list_objects_v2(
            Bucket=self.bucket,
            Prefix=prefix,
            Delimiter="/",
        )

        children: list[S3Item] = []
        for common in response.get("CommonPrefixes", []):
            child_prefix = str(common.get("Prefix", ""))
            if child_prefix and child_prefix != prefix:
                children.append(
                    S3Item(
                        client=self.client,
                        bucket=self.bucket,
                        key=child_prefix,
                        is_directory=True,
                    )
                )

        for item in response.get("Contents", []):
            child_key = str(item.get("Key", ""))
            if not child_key or child_key == prefix or child_key.endswith("/"):
                continue
            children.append(
                S3Item(
                    client=self.client,
                    bucket=self.bucket,
                    key=child_key,
                    is_directory=False,
                )
            )

        self._children = sorted(children, key=lambda child: (child.path, child.name))
        return self

    def download(self, target_dir: str | Path) -> None:
        if self.is_directory:
            super().download(target_dir)
            return
        target = Path(target_dir)
        if target.is_dir():
            target = target / self.name
        target.parent.mkdir(parents=True, exist_ok=True)
        self.client.client.download_file(self.bucket, self.key, str(target))


__all__ = [
    "S3Client",
    "S3Item",
    "check_s3_credentials",
]
