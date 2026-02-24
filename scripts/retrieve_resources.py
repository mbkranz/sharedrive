# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "python-dotenv>=1.0.0",
#   "sharedrive",
#   "pydantic>=2.10.6",
#   "pyyaml>=6.0",
#   "load_dotenv",
# #  "cloudpathlib",
#   "boto3"
# ]
# [tool.uv.sources]
# # sharedrive = { git = "https://github.com/NORCUChicago/sharedrive.git" }
# # To use a local checkout instead, swap the line above for:
# sharedrive = { path = "../../sharedrive", editable = true }
# ///

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import boto3
import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field, SecretStr, field_validator
# from cloudpathlib import S3Path


from pmd_utils.io.adapters.sharepoint import SharepointClient

load_dotenv()
AZURE_TENANT_ID = os.getenv("AZURE_TENANT_ID")
AZURE_CLIENT_ID = os.getenv("AZURE_CLIENT_ID")
AZURE_CLIENT_SECRET = os.getenv("AZURE_CLIENT_SECRET")

class SpoConfig(BaseModel):
    tenant_id: str = Field(default=AZURE_TENANT_ID)
    client_id: str = Field(default=AZURE_CLIENT_ID)
    client_secret: SecretStr | None = Field(default=AZURE_CLIENT_SECRET)
    scope: list[str] = Field(default=["https://graph.microsoft.com/.default"])
    user_delegated_access: bool = Field(default=True)

    @field_validator("scope", mode="before")
    @classmethod
    def to_list(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, str):
            return [value]
        return value
    
    def to_client(self) -> SharepointClient:
        return SharepointClient(
            tenant_id=self.tenant_id,
            client_id=self.client_id,
            client_secret=self.client_secret,
            host_url="",
            scope=self.scope,
            user_delegated_access=self.user_delegated_access,
        )


def load_descriptor(path: Path) -> list[dict[str, Any]]:
    descriptor_text = path.read_text(encoding="utf-8")
    suffix = path.suffix.lower()

    if suffix == ".json":
        data = json.loads(descriptor_text)
    elif suffix in {".yaml", ".yml"}:
        data = yaml.safe_load(descriptor_text)
    else:
        try:
            data = json.loads(descriptor_text)
        except json.JSONDecodeError:
            data = yaml.safe_load(descriptor_text)

    if not isinstance(data, dict):
        raise ValueError("Descriptor must be a top-level JSON/YAML object")

    resources = data.get("resources")
    if not isinstance(resources, list):
        raise ValueError("Descriptor must contain a top-level 'resources' array")
    return resources


def resolve_default_descriptor() -> Path:
    for candidate in (
        Path("resources/descriptor.yaml"),
        Path("resources/descriptor.yml"),
        Path("resources/descriptor.json"),
    ):
        if candidate.exists():
            return candidate
    return Path("resources/descriptor.json")


def resource_source_url(resource: dict[str, Any]) -> str | None:
    sources = resource.get("sources")
    if isinstance(sources, list):
        for source_obj in sources:
            if isinstance(source_obj, dict):
                source_path = source_obj.get("path")
                if isinstance(source_path, str) and source_path.strip():
                    return source_path.strip()

    legacy_source = resource.get("source")
    if isinstance(legacy_source, str) and legacy_source.strip():
        return legacy_source.strip()
    return None


def resource_output_path(resource: dict[str, Any], output_dir: Path) -> Path:
    path_value = resource.get("path")
    if not isinstance(path_value, str) or not path_value.strip():
        raise ValueError("Resource is missing required string field 'path'")

    path = Path(path_value.strip())
    if path.is_absolute():
        return path
    return output_dir / path


def resource_adapter_name(resource: dict[str, Any], source_url: str | None) -> str:
    adapter = resource.get("x-adapter")
    if isinstance(adapter, str) and adapter.strip():
        return adapter.strip().lower()

    if not source_url:
        return "unknown"
    
    if urlparse(source_url).scheme == "s3":
        return "s3"

    host = urlparse(source_url).netloc.lower()
    if "sharepoint.com" in host:
        return "sharepoint"
    if host.startswith("www."):
        host = host[4:]
    return host.split(".")[0] if host else "unknown"


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

def run(dry_run: bool, descriptor: Path|str, include_types: str|list[str] = "all") -> None:

    if isinstance(descriptor,Path):
        resources = load_descriptor(descriptor)
        os.chdir(descriptor.parent)
    elif isinstance(descriptor, str):
        resources = load_descriptor(Path(descriptor))
        os.chdir(Path(descriptor).parent)
    else:
        raise ValueError("Descriptor must be a Path or string")
    failures = 0

    for index, resource in enumerate(resources):
        if not isinstance(resource, dict):
            print(f"Warning, resource[{index}] is not an object")
            failures += 1
            continue

        resource_name = resource.get("name", f"resource[{index}]")
        source_url = resource_source_url(resource)
        adapter_name = resource_adapter_name(resource, source_url)

        try:
            output_path = resource_output_path(resource, output_dir)
        except Exception as exc:
            print(f"Warning, {resource_name} invalid path: {exc}")
            failures += 1
            continue

        if not adapter_name in include_types and not include_types == ["all"]:
            print(f"Skipping {resource_name} with adapter '{adapter_name}' not in include set of {str(include_types) }")
            continue
        if not source_url:
            print(f"Warning, {resource_name} has no source URL")
            failures += 1
            continue

        if adapter_name == "sharepoint":
            client = SpoConfig().to_client()
            client.download_from_weburl(url=source_url, output_path=output_path, dry_run=dry_run)
        elif adapter_name == "s3":
            client = boto3.client("s3")
            bucket, key = parse_s3_source_url(source_url)
            print(f"Parsed S3 bucket: '{bucket}', key: '{key}'")
            
            if dry_run:
                print(f"Would download {source_url} to {output_path}")
            else:
                print(f"Downloading {source_url} to {output_path}")

                output_path.parent.mkdir(parents=True, exist_ok=True)
                client.download_file(bucket, key, str(output_path))

        else:
            print(f"Warning, {resource_name} has unrecognized adapter '{adapter_name}' for URL '{source_url}'")
            failures += 1
            continue


if __name__ == "__main__":

    parser = argparse.ArgumentParser(description="Retrieve resources specified in a descriptor file")
    parser.add_argument(
        "--descriptor",
        type=Path,
        default=resolve_default_descriptor(),
        help="Path to the resource descriptor JSON or YAML file",
    )
    parser.add_argument("--include", type=str, default="all",choices=["background","output","all","s3","sharepoint"], help="Type of resources to retrieve (default: all)")
    parser.add_argument("--output-dir", type=Path, default=Path("resources"), help="Directory to save retrieved resources")
    parser.add_argument("--dry-run", action="store_true", help="Print actions without performing retrieval")
    args = parser.parse_args()

    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    run(dry_run=args.dry_run, descriptor=args.descriptor, include_types=[args.include] if args.include == "all" else [args.include])
