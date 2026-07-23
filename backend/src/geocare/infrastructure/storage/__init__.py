"""File storage abstraction and implementations."""

import os
import shutil
import uuid
from abc import ABC, abstractmethod
from pathlib import Path
from typing import AsyncGenerator, BinaryIO, Optional

import aiofiles

from geocare.config.settings import settings


class FileStoragePort(ABC):
    """Abstract file storage interface."""

    @abstractmethod
    async def save_file(
        self,
        content: bytes,
        filename: str,
        subdir: str = "",
    ) -> str:
        """Save file and return storage path."""
        ...

    @abstractmethod
    async def save_file_stream(
        self,
        file: BinaryIO,
        filename: str,
        subdir: str = "",
    ) -> str:
        """Save file from stream and return storage path."""
        ...

    @abstractmethod
    async def get_file(self, path: str) -> bytes:
        """Retrieve file content."""
        ...

    @abstractmethod
    async def stream_file(self, path: str) -> AsyncGenerator[bytes, None]:
        """Stream file content in chunks."""
        ...

    @abstractmethod
    async def delete_file(self, path: str) -> bool:
        """Delete file."""
        ...

    @abstractmethod
    async def file_exists(self, path: str) -> bool:
        """Check if file exists."""
        ...

    @abstractmethod
    async def get_file_size(self, path: str) -> int:
        """Get file size in bytes."""
        ...

    @abstractmethod
    async def generate_presigned_url(
        self,
        path: str,
        expiration: int = 3600,
    ) -> str:
        """Generate time-limited download URL."""
        ...

    @abstractmethod
    async def save_metadata(
        self,
        file_id: str,
        metadata: dict,
    ) -> str:
        """Save file metadata as JSON and return path."""
        ...

    @abstractmethod
    async def get_metadata(
        self,
        file_id: str,
    ) -> Optional[dict]:
        """Retrieve file metadata by file ID. Returns None if not found."""
        ...


class LocalStorageClient(FileStoragePort):
    """Local filesystem storage implementation."""

    def __init__(self, base_path: Optional[Path] = None):
        if base_path:
            self.base_path = base_path
        else:
            configured = settings.UPLOAD_DIR
            resolved = Path(configured)
            try:
                resolved.mkdir(parents=True, exist_ok=True)
                self.base_path = resolved
            except (OSError, PermissionError):
                import tempfile
                self.base_path = Path(tempfile.gettempdir()) / "geocare-uploads"
                self.base_path.mkdir(parents=True, exist_ok=True)

    def _resolve_path(self, path: str) -> Path:
        """Resolve relative path to absolute path."""
        return self.base_path / path

    async def save_file(
        self,
        content: bytes,
        filename: str,
        subdir: str = "",
    ) -> str:
        """Save file to local filesystem."""
        subdir_path = self.base_path / subdir
        subdir_path.mkdir(parents=True, exist_ok=True)

        # Generate unique filename
        file_ext = Path(filename).suffix
        unique_name = f"{uuid.uuid4().hex}{file_ext}"
        file_path = subdir_path / unique_name

        async with aiofiles.open(file_path, "wb") as f:
            await f.write(content)

        # Return relative path
        return str(Path(subdir) / unique_name)

    async def save_file_stream(
        self,
        file: BinaryIO,
        filename: str,
        subdir: str = "",
    ) -> str:
        """Save file from stream."""
        subdir_path = self.base_path / subdir
        subdir_path.mkdir(parents=True, exist_ok=True)

        file_ext = Path(filename).suffix
        unique_name = f"{uuid.uuid4().hex}{file_ext}"
        file_path = subdir_path / unique_name

        async with aiofiles.open(file_path, "wb") as f:
            while chunk := file.read(8192):
                await f.write(chunk)

        return str(Path(subdir) / unique_name)

    async def get_file(self, path: str) -> bytes:
        """Read file content."""
        file_path = self._resolve_path(path)
        async with aiofiles.open(file_path, "rb") as f:
            return await f.read()

    async def stream_file(self, path: str) -> AsyncGenerator[bytes, None]:
        """Stream file in chunks."""
        file_path = self._resolve_path(path)
        async with aiofiles.open(file_path, "rb") as f:
            while chunk := await f.read(8192):
                yield chunk

    async def delete_file(self, path: str) -> bool:
        """Delete file."""
        file_path = self._resolve_path(path)
        try:
            file_path.unlink(missing_ok=True)
            return True
        except Exception:
            return False

    async def file_exists(self, path: str) -> bool:
        """Check if file exists."""
        return self._resolve_path(path).exists()

    async def get_file_size(self, path: str) -> int:
        """Get file size."""
        file_path = self._resolve_path(path)
        return file_path.stat().st_size if file_path.exists() else 0

    async def generate_presigned_url(
        self,
        path: str,
        expiration: int = 3600,
    ) -> str:
        """Generate local file URL (served by FastAPI)."""
        # In production, this would be a proper signed URL
        return f"/api/v1/files/{path}/download"

    async def save_metadata(
        self,
        file_id: str,
        metadata: dict,
    ) -> str:
        """Save file metadata as JSON sidecar file."""
        import json
        metadata_path = self.base_path / ".metadata" / f"{file_id}.json"
        metadata_path.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps(metadata, indent=2, default=str)
        async with aiofiles.open(metadata_path, "w") as f:
            await f.write(text)
        return str(metadata_path.relative_to(self.base_path))

    async def get_metadata(
        self,
        file_id: str,
    ) -> Optional[dict]:
        """Retrieve file metadata by file ID."""
        import json
        metadata_path = self.base_path / ".metadata" / f"{file_id}.json"
        if not metadata_path.exists():
            return None
        async with aiofiles.open(metadata_path, "r") as f:
            text = await f.read()
        return json.loads(text)


class S3StorageClient(FileStoragePort):
    """S3-compatible storage implementation."""

    def __init__(
        self,
        bucket: str,
        region: str = "us-east-1",
        endpoint_url: Optional[str] = None,
        access_key: Optional[str] = None,
        secret_key: Optional[str] = None,
    ):
        self.bucket = bucket
        self.region = region
        self.endpoint_url = endpoint_url

        # Lazy import boto3
        try:
            import boto3
            self.s3 = boto3.client(
                "s3",
                region_name=region,
                endpoint_url=endpoint_url,
                aws_access_key_id=access_key,
                aws_secret_access_key=secret_key,
            )
        except ImportError:
            raise RuntimeError("boto3 required for S3 storage. Install with: pip install boto3")

    async def save_file(
        self,
        content: bytes,
        filename: str,
        subdir: str = "",
    ) -> str:
        """Upload file to S3."""
        key = f"{subdir}/{uuid.uuid4().hex}{Path(filename).suffix}".lstrip("/")
        self.s3.put_object(Bucket=self.bucket, Key=key, Body=content)
        return key

    async def save_file_stream(
        self,
        file: BinaryIO,
        filename: str,
        subdir: str = "",
    ) -> str:
        """Upload file stream to S3."""
        key = f"{subdir}/{uuid.uuid4().hex}{Path(filename).suffix}".lstrip("/")
        self.s3.upload_fileobj(file, self.bucket, key)
        return key

    async def get_file(self, path: str) -> bytes:
        """Download file from S3."""
        response = self.s3.get_object(Bucket=self.bucket, Key=path)
        return response["Body"].read()

    async def stream_file(self, path: str) -> AsyncGenerator[bytes, None]:
        """Stream file from S3."""
        response = self.s3.get_object(Bucket=self.bucket, Key=path)
        for chunk in response["Body"].iter_chunks(chunk_size=8192):
            yield chunk

    async def delete_file(self, path: str) -> bool:
        """Delete file from S3."""
        try:
            self.s3.delete_object(Bucket=self.bucket, Key=path)
            return True
        except Exception:
            return False

    async def file_exists(self, path: str) -> bool:
        """Check if file exists in S3."""
        try:
            self.s3.head_object(Bucket=self.bucket, Key=path)
            return True
        except Exception:
            return False

    async def get_file_size(self, path: str) -> int:
        """Get file size from S3."""
        try:
            response = self.s3.head_object(Bucket=self.bucket, Key=path)
            return response["ContentLength"]
        except Exception:
            return 0

    async def generate_presigned_url(
        self,
        path: str,
        expiration: int = 3600,
    ) -> str:
        """Generate presigned S3 URL."""
        return self.s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": path},
            ExpiresIn=expiration,
        )

    async def save_metadata(
        self,
        file_id: str,
        metadata: dict,
    ) -> str:
        """Save file metadata as JSON in S3."""
        import json
        key = f".metadata/{file_id}.json"
        self.s3.put_object(Bucket=self.bucket, Key=key, Body=json.dumps(metadata, default=str), ContentType="application/json")
        return key

    async def get_metadata(
        self,
        file_id: str,
    ) -> Optional[dict]:
        """Retrieve file metadata by file ID from S3."""
        import json
        key = f".metadata/{file_id}.json"
        try:
            response = self.s3.get_object(Bucket=self.bucket, Key=key)
            return json.loads(response["Body"].read())
        except Exception:
            return None


# Factory function
def get_storage_client() -> FileStoragePort:
    """Get configured storage client."""
    if settings.S3_BUCKET:
        return S3StorageClient(
            bucket=settings.S3_BUCKET,
            region=settings.S3_REGION,
            endpoint_url=settings.S3_ENDPOINT_URL,
            access_key=settings.S3_ACCESS_KEY,
            secret_key=settings.S3_SECRET_KEY,
        )
    return LocalStorageClient()