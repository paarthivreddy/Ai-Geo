# Queue port interface
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional


class QueuePort(ABC):
    """Abstract queue interface for background job processing."""

    @abstractmethod
    async def enqueue(
        self,
        task_name: str,
        *args: Any,
        queue: str = "default",
        priority: int = 0,
        delay: Optional[int] = None,
        **kwargs: Any,
    ) -> str:
        """Enqueue a task for background processing."""
        ...

    @abstractmethod
    async def get_result(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Get task result."""
        ...

    @abstractmethod
    async def revoke(self, task_id: str) -> bool:
        """Revoke/cancel a queued task."""
        ...

    @abstractmethod
    async def get_queue_stats(self, queue: str) -> Dict[str, Any]:
        """Get queue statistics."""
        ...


class ProgressPublisherPort(ABC):
    """Interface for publishing progress updates."""

    @abstractmethod
    async def publish_progress(
        self,
        job_id: str,
        processed: int,
        total: int,
        current_batch: int,
        total_batches: int,
    ) -> None:
        """Publish progress update."""
        ...

    @abstractmethod
    async def publish_status(
        self,
        job_id: str,
        status: str,
        error: Optional[str] = None,
    ) -> None:
        """Publish status change."""
        ...

    @abstractmethod
    async def publish_batch_complete(
        self,
        job_id: str,
        batch_index: int,
        succeeded: int,
        failed: int,
    ) -> None:
        """Publish batch completion."""
        ...