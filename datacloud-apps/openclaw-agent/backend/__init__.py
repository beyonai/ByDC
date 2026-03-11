"""datacloud-agent-service package.

FastAPI Gateway Service Layer for OpenClaw.
"""

from config import settings
from server import app, create_app

__version__ = "0.1.0"
__all__ = [
    "__version__",
    "app",
    "create_app",
    "settings",
]
