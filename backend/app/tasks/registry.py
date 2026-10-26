import inspect
import asyncio
from typing import Callable, Dict, Any, List, Optional


class UnregisteredTaskError(KeyError):
    """Raised when a worker attempts to execute a task type that is not registered."""
    def __init__(self, task_type: str):
        self.task_type = task_type
        super().__init__(
            f"Task type '{task_type}' is not registered. "
            f"Only predefined registered tasks can be executed by workers."
        )


# Global in-memory registry of safe task handlers
_TASK_REGISTRY: Dict[str, Callable[[Dict[str, Any]], Any]] = {}


def register_task(name: str) -> Callable:
    """
    Decorator to register a function as a safe task handler.
    Supports both synchronous and asynchronous callables.
    """
    def decorator(fn: Callable[[Dict[str, Any]], Any]) -> Callable:
        if name in _TASK_REGISTRY:
            raise ValueError(f"Task '{name}' is already registered to {_TASK_REGISTRY[name]}.")
        _TASK_REGISTRY[name] = fn
        return fn

    return decorator


def get_task_handler(name: str) -> Callable[[Dict[str, Any]], Any]:
    """Retrieves a registered task handler by name. Raises UnregisteredTaskError if not found."""
    if name not in _TASK_REGISTRY:
        raise UnregisteredTaskError(name)
    return _TASK_REGISTRY[name]


def list_registered_tasks() -> List[str]:
    """Returns a sorted list of all registered task names."""
    return sorted(list(_TASK_REGISTRY.keys()))


async def execute_task_handler(fn: Callable[[Dict[str, Any]], Any], payload: Dict[str, Any]) -> Any:
    """Helper to execute either async or sync task handlers seamlessly."""
    if inspect.iscoroutinefunction(fn):
        return await fn(payload)
    else:
        # Run synchronous blocking function in the default threadpool executor
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, fn, payload)
