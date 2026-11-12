"""
SAIS Storage Service — Phase 8C
Handles storage operations across Supabase Storage and local disk fallback.
"""
from __future__ import annotations

import logging
import os
import aiofiles
import httpx
from typing import Optional, Protocol

from app.config import settings

logger = logging.getLogger("sais.storage")


class StorageDriver(Protocol):
    async def upload_file(self, bucket: str, path: str, content: bytes, content_type: str) -> str:
        ...

    async def download_file(self, bucket: str, path: str) -> bytes:
        ...

    async def delete_file(self, bucket: str, path: str) -> bool:
        ...

    async def create_signed_url(self, bucket: str, path: str, expires_in: int = 300) -> str:
        ...

    async def check_bucket_exists(self, bucket: str) -> bool:
        ...

    async def list_files(self, bucket: str, prefix: str = "") -> list[str]:
        ...


class SupabaseStorageDriver:
    """Async Supabase Storage client using standard REST API via httpx."""

    def __init__(self, url: str, service_role_key: str):
        self.base_url = url.rstrip("/")
        self.service_role_key = service_role_key
        self.headers = {
            "Authorization": f"Bearer {self.service_role_key}",
            "apikey": self.service_role_key,
        }

    async def check_bucket_exists(self, bucket: str) -> bool:
        """
        Verify that the bucket exists and is private (never public).
        Raises RuntimeError if the bucket is public.
        """
        endpoint = f"{self.base_url}/storage/v1/bucket/{bucket}"
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(endpoint, headers=self.headers)
            if resp.status_code == 404:
                return False
            resp.raise_for_status()
            data = resp.json()
            if data.get("public") is True:
                raise RuntimeError(
                    f"Security violation: Supabase bucket '{bucket}' is public! "
                    "SAIS requires all storage buckets to be strictly private."
                )
            return True

    async def upload_file(self, bucket: str, path: str, content: bytes, content_type: str) -> str:
        """Upload raw file bytes to private bucket path."""
        clean_path = path.lstrip("/")
        endpoint = f"{self.base_url}/storage/v1/object/{bucket}/{clean_path}"
        headers = dict(self.headers)
        headers["Content-Type"] = content_type
        headers["x-upsert"] = "true"

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(endpoint, headers=headers, content=content)
            if resp.status_code not in (200, 201):
                logger.error("Supabase Storage upload failed: %s %s", resp.status_code, resp.text)
                resp.raise_for_status()
        return clean_path

    async def download_file(self, bucket: str, path: str) -> bytes:
        """Download file bytes from private bucket."""
        clean_path = path.lstrip("/")
        endpoint = f"{self.base_url}/storage/v1/object/authenticated/{bucket}/{clean_path}"
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(endpoint, headers=self.headers)
            resp.raise_for_status()
            return resp.content

    async def delete_file(self, bucket: str, path: str) -> bool:
        """
        Delete a file from the private bucket.
        Returns True if deleted, False if error.
        """
        clean_path = path.lstrip("/")
        endpoint = f"{self.base_url}/storage/v1/object/{bucket}"
        payload = {"prefixes": [clean_path]}
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.request("DELETE", endpoint, headers=self.headers, json=payload)
                if resp.status_code not in (200, 204):
                    logger.warning("Supabase Storage delete failed for %s: %s", clean_path, resp.text)
                    return False
                return True
        except Exception as exc:
            logger.warning("Supabase Storage delete request failed for %s: %s", clean_path, exc)
            return False

    async def create_signed_url(self, bucket: str, path: str, expires_in: int = 300) -> str:
        """Generate a short-lived signed URL for reading private file."""
        clean_path = path.lstrip("/")
        endpoint = f"{self.base_url}/storage/v1/object/sign/{bucket}/{clean_path}"
        payload = {"expiresIn": expires_in}
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(endpoint, headers=self.headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
            signed_url_path = data.get("signedURL")
            if not signed_url_path:
                raise RuntimeError("Failed to obtain signedURL from Supabase Storage")
            # Supabase returns relative or absolute path
            if signed_url_path.startswith("http"):
                return signed_url_path
            return f"{self.base_url}/storage/v1{signed_url_path}"

    async def list_files(self, bucket: str, prefix: str = "") -> list[str]:
        """List object keys matching prefix in bucket."""
        endpoint = f"{self.base_url}/storage/v1/object/list/{bucket}"
        payload = {"prefix": prefix, "limit": 1000}
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(endpoint, headers=self.headers, json=payload)
            resp.raise_for_status()
            items = resp.json()
            return [f"{prefix.rstrip('/')}/{item['name']}".lstrip('/') for item in items if "name" in item]


class LocalStorageDriver:
    """Local disk driver for offline development."""

    def __init__(self, base_dir: Optional[str] = None):
        self.base_dir = base_dir or settings.UPLOAD_DIR
        os.makedirs(self.base_dir, exist_ok=True)

    def _resolve_path(self, bucket: str, path: str) -> str:
        clean_path = path.lstrip("/").replace("/", os.sep)
        full_path = os.path.join(self.base_dir, bucket, clean_path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        return full_path

    async def check_bucket_exists(self, bucket: str) -> bool:
        bucket_dir = os.path.join(self.base_dir, bucket)
        os.makedirs(bucket_dir, exist_ok=True)
        return True

    async def upload_file(self, bucket: str, path: str, content: bytes, content_type: str) -> str:
        clean_path = path.lstrip("/")
        full_path = self._resolve_path(bucket, clean_path)
        async with aiofiles.open(full_path, "wb") as f:
            await f.write(content)
        return clean_path

    async def download_file(self, bucket: str, path: str) -> bytes:
        clean_path = path.lstrip("/")
        full_path = self._resolve_path(bucket, clean_path)
        if not os.path.isfile(full_path):
            raise FileNotFoundError(f"Local file not found: {clean_path}")
        async with aiofiles.open(full_path, "rb") as f:
            return await f.read()

    async def delete_file(self, bucket: str, path: str) -> bool:
        clean_path = path.lstrip("/")
        full_path = self._resolve_path(bucket, clean_path)
        try:
            if os.path.isfile(full_path):
                os.remove(full_path)
                return True
            return False
        except Exception as exc:
            logger.warning("Local delete failed for %s: %s", full_path, exc)
            return False

    async def create_signed_url(self, bucket: str, path: str, expires_in: int = 300) -> str:
        clean_path = path.lstrip("/")
        return f"file://local-storage/{bucket}/{clean_path}"

    async def list_files(self, bucket: str, prefix: str = "") -> list[str]:
        bucket_dir = os.path.join(self.base_dir, bucket)
        if not os.path.isdir(bucket_dir):
            return []
        matched = []
        for root, _, files in os.walk(bucket_dir):
            for file in files:
                full = os.path.join(root, file)
                rel = os.path.relpath(full, bucket_dir).replace(os.sep, "/")
                if rel.startswith(prefix):
                    matched.append(rel)
        return matched


class FakeStorageDriver:
    """In-memory driver for unit tests. Requires zero network and zero keys."""

    def __init__(self):
        self.files: dict[str, bytes] = {}
        self.content_types: dict[str, str] = {}
        self.deleted_keys: list[str] = []
        self.should_fail_delete: bool = False

    def _key(self, bucket: str, path: str) -> str:
        return f"{bucket}/{path.lstrip('/')}"

    async def check_bucket_exists(self, bucket: str) -> bool:
        return True

    async def upload_file(self, bucket: str, path: str, content: bytes, content_type: str) -> str:
        key = self._key(bucket, path)
        self.files[key] = content
        self.content_types[key] = content_type
        return path.lstrip("/")

    async def download_file(self, bucket: str, path: str) -> bytes:
        key = self._key(bucket, path)
        if key not in self.files:
            raise FileNotFoundError(f"File not found in fake storage: {key}")
        return self.files[key]

    async def delete_file(self, bucket: str, path: str) -> bool:
        if self.should_fail_delete:
            return False
        key = self._key(bucket, path)
        self.deleted_keys.append(key)
        if key in self.files:
            del self.files[key]
            self.content_types.pop(key, None)
            return True
        return False

    async def create_signed_url(self, bucket: str, path: str, expires_in: int = 300) -> str:
        return f"https://fake-supabase-storage.test/{bucket}/{path.lstrip('/')}?token=mock-exp-{expires_in}"

    async def list_files(self, bucket: str, prefix: str = "") -> list[str]:
        pfx = f"{bucket}/{prefix}".rstrip("/")
        results = []
        for k in self.files:
            if k.startswith(pfx):
                # return relative to bucket
                rel = k[len(bucket) + 1:]
                results.append(rel)
        return results


_driver_instance: Optional[StorageDriver] = None


def get_storage_service() -> StorageDriver:
    """Get or initialize the global storage driver based on configuration."""
    global _driver_instance
    if _driver_instance is not None:
        return _driver_instance

    backend = (settings.STORAGE_BACKEND or "supabase").strip().lower()
    if backend == "local":
        _driver_instance = LocalStorageDriver()
        logger.info("StorageService initialized with LocalStorageDriver (dir=%s)", settings.UPLOAD_DIR)
    elif backend == "fake":
        _driver_instance = FakeStorageDriver()
        logger.info("StorageService initialized with FakeStorageDriver")
    elif backend == "supabase":
        if not settings.SUPABASE_URL or not settings.SUPABASE_SERVICE_ROLE_KEY:
            raise RuntimeError(
                "STORAGE_BACKEND is set to 'supabase' but SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY is missing. "
                "Configure them in backend/.env or set STORAGE_BACKEND=local for local development."
            )
        _driver_instance = SupabaseStorageDriver(
            url=settings.SUPABASE_URL,
            service_role_key=settings.SUPABASE_SERVICE_ROLE_KEY,
        )
        logger.info("StorageService initialized with SupabaseStorageDriver (bucket=%s)", settings.SUPABASE_STORAGE_BUCKET)
    else:
        raise ValueError(f"Unknown STORAGE_BACKEND '{backend}'. Allowed: 'supabase', 'local', 'fake'.")

    return _driver_instance


def set_storage_service(driver: Optional[StorageDriver]) -> None:
    """Override storage service (used by tests)."""
    global _driver_instance
    _driver_instance = driver

