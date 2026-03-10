"""Command router for OpenClaw Gateway.

Provides CommandResult dataclass and CommandRouter class for parsing
and executing slash commands.
"""

from __future__ import annotations

import shlex
from dataclasses import dataclass
from typing import Any, Callable


@dataclass
class CommandResult:
    """Result of parsing a command.

    Attributes:
        command: The command name (without the leading slash)
        args: List of arguments (parsed with shell-like quoting support)
        raw: The original command string
    """

    command: str
    args: list[str]
    raw: str


class CommandRouter:
    """Router for parsing and executing slash commands.

    Supports built-in commands:
        - /model <agent_id> - Switch to specified agent
        - /reset - Reset current session
        - /help - Show help message
        - /clear - Clear conversation history

    Features:
        - Commands start with /
        - Support arguments separated by spaces
        - Support quoted arguments (e.g., /model "my agent")
        - Case-insensitive command matching
    """

    def __init__(self) -> None:
        """Initialize the command router."""
        self._handlers: dict[str, Callable[[list[str]], Any]] = {}
        self._register_builtin_handlers()

    def _register_builtin_handlers(self) -> None:
        """Register built-in command handlers."""

        def model_handler(args: list[str]) -> str:
            if not args:
                return "Usage: /model <agent_id>"
            return f"Switching to agent: {args[0]}"

        def reset_handler(_args: list[str]) -> str:
            return "Session reset"

        def help_handler(_args: list[str]) -> str:
            help_text = """Available commands:
/model <agent_id> - Switch to specified agent
/reset - Reset current session
/help - Show this help message
/clear - Clear conversation history"""
            return help_text

        def clear_handler(_args: list[str]) -> str:
            return "Conversation history cleared"

        self._handlers["model"] = model_handler
        self._handlers["reset"] = reset_handler
        self._handlers["help"] = help_handler
        self._handlers["clear"] = clear_handler

    def is_command(self, text: str) -> bool:
        """Check if text is a command.

        Args:
            text: The text to check

        Returns:
            True if text starts with /
        """
        if not text:
            return False
        return text.strip().startswith("/")

    def parse_command(self, text: str) -> CommandResult | None:
        """Parse slash command from text.

        Args:
            text: The text to parse

        Returns:
            CommandResult if text is a valid command, None otherwise
        """
        if not self.is_command(text):
            return None

        stripped = text.strip()
        if not stripped.startswith("/"):
            return None

        # Remove the leading slash
        command_part = stripped[1:]

        # Handle empty command
        if not command_part:
            return None

        try:
            # Use shlex for proper shell-like parsing (handles quoted args)
            args = shlex.split(command_part)
        except ValueError:
            # Invalid quoting, treat entire thing as command
            args = command_part.split()

        if not args:
            return None

        # Command is case-insensitive
        command = args[0].lower()
        command_args = args[1:] if len(args) > 1 else []

        return CommandResult(command=command, args=command_args, raw=text)

    def register_handler(self, command: str, handler: Callable[[list[str]], Any]) -> None:
        """Register a custom command handler.

        Args:
            command: The command name (will be lowercased)
            handler: The handler function that takes args list and returns Any
        """
        self._handlers[command.lower()] = handler

    def execute(self, command: str, args: list[str]) -> Any:
        """Execute a command handler.

        Args:
            command: The command name (case-insensitive)
            args: The arguments to pass to the handler

        Returns:
            The result from the handler, or error message if command not found

        Raises:
            KeyError: If command is not registered
        """
        command_lower = command.lower()
        if command_lower not in self._handlers:
            return f"Unknown command: /{command}"

        handler = self._handlers[command_lower]
        return handler(args)
