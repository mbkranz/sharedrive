from __future__ import annotations

from pathlib import Path
from typing import ClassVar
from urllib.parse import urlparse

import boto3
from botocore.exceptions import ClientError

try:
    from cloudpathlib import S3Path
except ImportError:  # pragma: no cover
    S3Path = None

from sharedrive.clients.base import BaseClient
from sharedrive.exceptions import S3Error
from sharedrive.item import DriveItem
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


def parse_s3_source_url(source_url: str) -> tuple[str, str]:
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

    if not bucket or not key:
        raise ValueError(f"Could not parse bucket/key from source URL: {source_url}")
    return bucket, key


def download_s3_url(
    source_url: str,
    output_path: Path,
    *,
    dry_run: bool = False,
    use_cloudpathlib: bool = True,
) -> Path | None:
    if dry_run:
        print(f"Would download {source_url} to {output_path}")
        return None

    output_path.parent.mkdir(parents=True, exist_ok=True)
    if use_cloudpathlib and S3Path is not None:
        S3Path(source_url).download_to(str(output_path))
        return output_path

    bucket, key = parse_s3_source_url(source_url)
    boto3.client("s3").download_file(bucket, key, str(output_path))
    return output_path


class S3Item(DriveItem):
    """A single S3 object (file) or common prefix (virtual folder).

    S3 does not have native directories; a "folder" is a common prefix
    (a key ending in ``/``) discovered via ``list_objects_v2``.  All
    read operations delegate to the owning :class:`S3Client`.

    Design note: mirrors
    :class:`~sharedrive.clients.sharepoint.SharepointItem` and
    ``GDriveItem`` – a single class handles both files and directories,
    with :attr:`is_directory` acting as the discriminator.
    """

    def __init__(
        self,
        bucket: str,
        key: str,
        *,
        is_prefix: bool,
        metadata: dict | None = None,
        client: "S3Client",
    ) -> None:
        self._bucket = bucket
        self._key = key
        self._is_prefix = is_prefix
        self._metadata = metadata or {}
        self._client = client
        self._children: list["S3Item"] | None = None

    # ------------------------------------------------------------------
    # DriveItem abstract properties
    # ------------------------------------------------------------------

    @property
    def id(self) -> str:
        return f"s3://{self._bucket}/{self._key}"

    @property
    def name(self) -> str:
        stripped = self._key.rstrip("/")
        return stripped.rsplit("/", 1)[-1] if "/" in stripped else stripped

    @property
    def path(self) -> str:
        return self._key

    @property
    def service_type(self) -> str:
        return "S3"

    @property
    def source_url(self) -> str:
        return f"s3://{self._bucket}/{self._key}"

    @property
    def is_directory(self) -> bool:
        return self._is_prefix

    # ------------------------------------------------------------------
    # Concrete behaviour
    # ------------------------------------------------------------------

    @property
    def children(self) -> list["S3Item"]:
        """Immediate children of this prefix; lazily fetched on first access."""
        if not self._is_prefix:
            return []
        if self._children is None:
            self._children = self._client._list_prefix_children(
                self._bucket, self._key
            )
        return self._children

    def refresh(self, *, include_children: bool = True) -> "S3Item":
        """Re-fetch metadata (and optionally children) from S3."""
        if not self._is_prefix:
            try:
                self._metadata = self._client._s3.head_object(
                    Bucket=self._bucket, Key=self._key
                )
            except ClientError as exc:
                raise S3Error(
                    f"Failed to refresh s3://{self._bucket}/{self._key}: {exc}"
                ) from exc
        elif include_children:
            self._children = self._client._list_prefix_children(
                self._bucket, self._key
            )
        return self

    def download(self, target: Path | str) -> None:
        """Download this item to *target*.

        For directory items, recursively walks children via the base-class
        :meth:`~sharedrive.item.DriveItem.download`.  For file items,
        delegates to ``s3.download_file``.
        """
        if self.is_directory:
            super().download(target)
            return
        target_path = Path(target)
        if target_path.is_dir():
            target_path = target_path / self.name
        target_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._client._s3.download_file(
                self._bucket, self._key, str(target_path)
            )
        except ClientError as exc:
            raise S3Error(
                f"Failed to download s3://{self._bucket}/{self._key}: {exc}"
            ) from exc


@provider("s3")
class S3Client(BaseClient):
    """S3 client backed by boto3, registered as the ``"s3"`` provider.

    Handles both ``s3://`` URIs and ``http(s)://`` S3 endpoint URLs.
    Credentials are resolved through the standard boto3 credential chain
    (environment variables, shared credentials file, IAM instance
    profiles, …).

    Instantiate directly or via :meth:`build_default`::

        client = S3Client()
        item   = client.get_from_weburl("s3://my-bucket/path/to/file.csv")
        item.download("local/file.csv")

        # Or via the provider registry:
        from sharedrive.registry import get_provider
        client = get_provider("s3").build_default()

    AWS credential chain:
        https://boto3.amazonaws.com/v1/documentation/api/latest/guide/credentials.html
    """

    auth_methods: ClassVar[list[str]] = ["env", "instance_profile", "assume_role"]

    def __init__(self, *, boto_session: boto3.Session | None = None) -> None:
        self._session = boto_session or boto3.Session()
        self._s3 = self._session.client("s3")

    @classmethod
    def build_default(cls) -> "S3Client":
        """Construct from the current boto3 credential chain.

        Reads AWS credentials from environment variables
        (``AWS_ACCESS_KEY_ID``, ``AWS_SECRET_ACCESS_KEY``,
        ``AWS_SESSION_TOKEN``), the shared credentials file, IAM instance
        profiles, or any other source supported by the boto3 chain.
        """
        return cls()

    @classmethod
    def check_auth(cls) -> None:
        """Validate that AWS credentials are available.

        Delegates to :func:`check_s3_credentials`; raises
        :exc:`RuntimeError` when credentials are missing or incomplete.
        """
        check_s3_credentials()

    def get_from_weburl(self, url: str) -> S3Item:
        """Return an :class:`S3Item` for the given ``s3://`` or http(s) URL.

        Keys ending with ``/`` (or an empty key after bucket) are returned
        as directory items immediately.  Otherwise ``HeadObject`` is tried
        first; a 404 causes a transparent fallback to treating the key as a
        virtual-folder prefix.
        """
        bucket, key = parse_s3_source_url(url)
        if not key or key.endswith("/"):
            return S3Item(bucket=bucket, key=key, is_prefix=True, client=self)
        try:
            metadata = self._s3.head_object(Bucket=bucket, Key=key)
            return S3Item(
                bucket=bucket, key=key, is_prefix=False, metadata=metadata, client=self
            )
        except ClientError as exc:
            error_code = exc.response.get("Error", {}).get("Code", "")
            # HeadObject returns HTTP 404 as error code "404"; GetObject/other
            # ops use "NoSuchKey". Check both for defence-in-depth.
            if error_code in ("404", "NoSuchKey"):
                prefix = key.rstrip("/") + "/"
                return S3Item(bucket=bucket, key=prefix, is_prefix=True, client=self)
            raise S3Error(f"Could not access s3://{bucket}/{key}: {exc}") from exc

    def _list_prefix_children(self, bucket: str, prefix: str) -> list[S3Item]:
        """List immediate children of an S3 prefix (one level deep).

        Uses ``list_objects_v2`` with a ``/`` delimiter so that nested
        prefixes appear as :class:`S3Item` directories rather than being
        flattened into the results.
        """
        results: list[S3Item] = []
        paginator = self._s3.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=bucket, Prefix=prefix, Delimiter="/"):
            for obj in page.get("Contents", []):
                key = obj["Key"]
                if key == prefix:  # skip directory-marker object
                    continue
                results.append(
                    S3Item(
                        bucket=bucket,
                        key=key,
                        is_prefix=False,
                        metadata=obj,
                        client=self,
                    )
                )
            for cp in page.get("CommonPrefixes", []):
                results.append(
                    S3Item(
                        bucket=bucket,
                        key=cp["Prefix"],
                        is_prefix=True,
                        client=self,
                    )
                )
        return results


__all__ = [
    "S3Client",
    "S3Item",
    "check_s3_credentials",
    "download_s3_url",
    "parse_s3_source_url",
]
