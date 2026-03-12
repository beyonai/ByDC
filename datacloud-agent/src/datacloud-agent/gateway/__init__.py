"""Gateway package — bridge between the task scheduler and the Agent core.

The task scheduler (third-party service) is *not* implemented here.
This package only contains the client-side adapters:

handler.py      Receive a raw task payload, rewrite the business question,
                initialise workspace + session, and hand off to orchestration.
task_adapter.py Client stub for pulling tasks from and pushing results back
                to the task scheduler API.
"""

from .handler import MessageHandler
from .task_adapter import TaskSchedulerClient

__all__ = ["MessageHandler", "TaskSchedulerClient"]
