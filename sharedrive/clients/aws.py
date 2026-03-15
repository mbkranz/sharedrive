from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

import boto3

try:
    from cloudpathlib import S3Path
except ImportError:  # pragma: no cover
    S3Path = None


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


__all__ = [
    "download_s3_url",
    "parse_s3_source_url",
]
