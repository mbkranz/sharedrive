from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError

from sharedrive.clients.aws import S3Client, S3Item, parse_s3_source_url
from sharedrive.clients.base import BaseClient
from sharedrive.exceptions import S3Error
from sharedrive.registry import get_provider


# ---------------------------------------------------------------------------
# parse_s3_source_url
# ---------------------------------------------------------------------------


def test_parse_s3_uri() -> None:
    bucket, key = parse_s3_source_url("s3://my-bucket/path/to/file.csv")
    assert bucket == "my-bucket"
    assert key == "path/to/file.csv"


def test_parse_https_path_style() -> None:
    bucket, key = parse_s3_source_url(
        "https://s3.amazonaws.com/my-bucket/data/file.parquet"
    )
    assert bucket == "my-bucket"
    assert key == "data/file.parquet"


def test_parse_https_virtual_hosted() -> None:
    bucket, key = parse_s3_source_url(
        "https://my-bucket.s3.amazonaws.com/data/file.csv"
    )
    assert bucket == "my-bucket"
    assert key == "data/file.csv"


def test_parse_unsupported_scheme_raises() -> None:
    with pytest.raises(ValueError, match="Unsupported URL scheme"):
        parse_s3_source_url("ftp://bucket/key")


def test_parse_unsupported_host_raises() -> None:
    with pytest.raises(ValueError, match="Unsupported S3 URL host"):
        parse_s3_source_url("https://example.com/bucket/key")


# ---------------------------------------------------------------------------
# S3Client – registry / BaseClient contract
# ---------------------------------------------------------------------------


def test_s3_client_is_registered_provider() -> None:
    import sharedrive.clients.aws  # noqa: F401

    cls = get_provider("s3")
    assert cls is S3Client


def test_s3_client_is_base_client() -> None:
    assert issubclass(S3Client, BaseClient)


def test_s3_client_auth_methods() -> None:
    assert "env" in S3Client.auth_methods
    assert "instance_profile" in S3Client.auth_methods
    assert "assume_role" in S3Client.auth_methods


def test_s3_client_build_default_returns_instance() -> None:
    with patch("sharedrive.clients.aws.boto3.Session"):
        client = S3Client.build_default()
    assert isinstance(client, S3Client)


def test_s3_client_check_auth_calls_check_s3_credentials() -> None:
    with patch("sharedrive.clients.aws.check_s3_credentials") as mock_check:
        S3Client.check_auth()
    mock_check.assert_called_once()


# ---------------------------------------------------------------------------
# S3Client – get_from_weburl
# ---------------------------------------------------------------------------


def _make_client() -> tuple[S3Client, MagicMock]:
    """Return an S3Client wired to a mock boto3 s3 sub-client."""
    mock_s3 = MagicMock()
    session = MagicMock()
    session.client.return_value = mock_s3
    client = S3Client(boto_session=session)
    return client, mock_s3


def test_get_from_weburl_file() -> None:
    client, mock_s3 = _make_client()
    mock_s3.head_object.return_value = {"ContentLength": 100, "ETag": "abc"}

    item = client.get_from_weburl("s3://my-bucket/data/file.csv")

    assert isinstance(item, S3Item)
    assert item.is_directory is False
    assert item.name == "file.csv"
    assert item.path == "data/file.csv"
    assert item.source_url == "s3://my-bucket/data/file.csv"
    assert item.service_type == "S3"
    assert item.id == "s3://my-bucket/data/file.csv"


def test_get_from_weburl_prefix_explicit() -> None:
    client, mock_s3 = _make_client()

    item = client.get_from_weburl("s3://my-bucket/data/folder/")

    assert item.is_directory is True
    assert item._key == "data/folder/"
    mock_s3.head_object.assert_not_called()


def test_get_from_weburl_fallback_to_prefix_on_404() -> None:
    client, mock_s3 = _make_client()
    error = ClientError({"Error": {"Code": "404", "Message": "Not Found"}}, "HeadObject")
    mock_s3.head_object.side_effect = error

    item = client.get_from_weburl("s3://my-bucket/data/folder")

    assert item.is_directory is True
    assert item._key == "data/folder/"


def test_get_from_weburl_raises_s3_error_on_other_client_error() -> None:
    client, mock_s3 = _make_client()
    error = ClientError({"Error": {"Code": "403", "Message": "Forbidden"}}, "HeadObject")
    mock_s3.head_object.side_effect = error

    with pytest.raises(S3Error):
        client.get_from_weburl("s3://my-bucket/private/file.csv")


# ---------------------------------------------------------------------------
# S3Item properties
# ---------------------------------------------------------------------------


def _make_file_item(key: str = "path/to/file.csv") -> S3Item:
    client, _ = _make_client()
    return S3Item(bucket="my-bucket", key=key, is_prefix=False, client=client)


def _make_dir_item(key: str = "path/to/folder/") -> S3Item:
    client, _ = _make_client()
    return S3Item(bucket="my-bucket", key=key, is_prefix=True, client=client)


def test_s3item_file_name() -> None:
    assert _make_file_item("path/to/file.csv").name == "file.csv"


def test_s3item_top_level_file_name() -> None:
    assert _make_file_item("top.parquet").name == "top.parquet"


def test_s3item_dir_name() -> None:
    assert _make_dir_item("path/to/folder/").name == "folder"


def test_s3item_file_is_not_directory() -> None:
    assert _make_file_item().is_directory is False


def test_s3item_dir_is_directory() -> None:
    assert _make_dir_item().is_directory is True


def test_s3item_file_children_is_empty() -> None:
    assert _make_file_item().children == []


def test_s3item_to_source() -> None:
    item = _make_file_item("data/file.csv")
    source = item.to_source()
    assert source.path == "s3://my-bucket/data/file.csv"
    assert source.serviceType == "S3"
    assert source.entityType == "File"


def test_s3item_to_resource() -> None:
    item = _make_file_item("data/file.csv")
    resource = item.to_resource()
    assert resource.path == "data/file.csv"


# ---------------------------------------------------------------------------
# S3Item – children (lazy fetch)
# ---------------------------------------------------------------------------


def test_s3item_dir_children_lazy_fetch() -> None:
    client, mock_s3 = _make_client()
    paginator = MagicMock()
    mock_s3.get_paginator.return_value = paginator
    paginator.paginate.return_value = [
        {
            "Contents": [{"Key": "folder/file1.csv"}, {"Key": "folder/file2.csv"}],
            "CommonPrefixes": [{"Prefix": "folder/sub/"}],
        }
    ]

    item = S3Item(bucket="my-bucket", key="folder/", is_prefix=True, client=client)
    children = item.children

    assert len(children) == 3
    file_children = [c for c in children if not c.is_directory]
    dir_children = [c for c in children if c.is_directory]
    assert len(file_children) == 2
    assert len(dir_children) == 1
    assert dir_children[0].name == "sub"


def test_s3item_dir_children_skips_directory_marker() -> None:
    client, mock_s3 = _make_client()
    paginator = MagicMock()
    mock_s3.get_paginator.return_value = paginator
    paginator.paginate.return_value = [
        {
            "Contents": [
                {"Key": "folder/"},  # directory marker – should be skipped
                {"Key": "folder/file.csv"},
            ],
            "CommonPrefixes": [],
        }
    ]

    item = S3Item(bucket="my-bucket", key="folder/", is_prefix=True, client=client)
    children = item.children

    assert len(children) == 1
    assert children[0].name == "file.csv"


# ---------------------------------------------------------------------------
# S3Item – download
# ---------------------------------------------------------------------------


def test_s3item_file_download(tmp_path: Path) -> None:
    client, mock_s3 = _make_client()
    item = S3Item(bucket="my-bucket", key="data/file.csv", is_prefix=False, client=client)

    item.download(tmp_path / "file.csv")

    mock_s3.download_file.assert_called_once_with(
        "my-bucket", "data/file.csv", str(tmp_path / "file.csv")
    )


def test_s3item_download_raises_s3_error_on_client_error(tmp_path: Path) -> None:
    client, mock_s3 = _make_client()
    error = ClientError({"Error": {"Code": "403", "Message": "Forbidden"}}, "GetObject")
    mock_s3.download_file.side_effect = error

    item = S3Item(bucket="my-bucket", key="data/file.csv", is_prefix=False, client=client)
    with pytest.raises(S3Error):
        item.download(tmp_path / "file.csv")


def test_s3item_refresh_file() -> None:
    client, mock_s3 = _make_client()
    mock_s3.head_object.return_value = {"ContentLength": 200}
    item = S3Item(bucket="my-bucket", key="data/file.csv", is_prefix=False, client=client)

    item.refresh()

    mock_s3.head_object.assert_called_once_with(Bucket="my-bucket", Key="data/file.csv")
    assert item._metadata["ContentLength"] == 200
