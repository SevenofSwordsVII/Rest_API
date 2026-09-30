"""Unified background task dispatcher abstraction adhering to Constitution Principle XV."""

import inspect
import logging
from abc import ABC, abstractmethod
from collections.abc import Callable, Coroutine
from typing import Any

from fastapi import BackgroundTasks

logger = logging.getLogger("core.tasks")


class TaskDispatcher(ABC):
    """Abstract interface for dispatching non-blocking background tasks."""

    @abstractmethod
    def dispatch(
        self,
        func: Callable[..., Any | Coroutine[Any, Any, Any]],
        *args: Any,
        **kwargs: Any,
    ) -> None:
        """Enqueue task for deferred background execution."""
        raise NotImplementedError


class FastAPIBackgroundTaskDispatcher(TaskDispatcher):
    """Dispatcher leveraging FastAPI's built-in in-process BackgroundTasks."""

    def __init__(self, background_tasks: BackgroundTasks) -> None:
        self.background_tasks = background_tasks

    def dispatch(
        self,
        func: Callable[..., Any | Coroutine[Any, Any, Any]],
        *args: Any,
        **kwargs: Any,
    ) -> None:
        async def _async_wrapper(*a: Any, **kw: Any) -> None:
            try:
                if inspect.iscoroutinefunction(func):
                    await func(*a, **kw)
                else:
                    func(*a, **kw)
            except Exception as exc:
                logger.exception("Background task failed: %s", exc)

        self.background_tasks.add_task(_async_wrapper, *args, **kwargs)


def get_task_dispatcher(background_tasks: BackgroundTasks) -> TaskDispatcher:
    """FastAPI dependency injecting the configured TaskDispatcher."""
    return FastAPIBackgroundTaskDispatcher(background_tasks)
