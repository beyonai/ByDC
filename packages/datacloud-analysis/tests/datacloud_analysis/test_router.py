"""Tests for CommandRouter."""

from datacloud_analysis.core import CommandRouter, CommandResult


class TestCommandResult:
    """Tests for CommandResult dataclass."""

    def test_command_result_creation(self):
        """Test creating a CommandResult."""
        result = CommandResult(command="model", args=["coder"], raw="/model coder")
        assert result.command == "model"
        assert result.args == ["coder"]
        assert result.raw == "/model coder"

    def test_command_result_with_multiple_args(self):
        """Test CommandResult with multiple arguments."""
        result = CommandResult(
            command="model",
            args=["agent", "with space"],
            raw='/model agent "with space"',
        )
        assert result.command == "model"
        assert result.args == ["agent", "with space"]


class TestCommandRouterIsCommand:
    """Tests for is_command method."""

    def test_is_command_with_slash(self):
        """Test is_command returns True for text starting with /."""
        router = CommandRouter()
        assert router.is_command("/model coder") is True
        assert router.is_command("/help") is True

    def test_is_command_without_slash(self):
        """Test is_command returns False for text without /."""
        router = CommandRouter()
        assert router.is_command("hello world") is False
        assert router.is_command("model coder") is False

    def test_is_command_empty(self):
        """Test is_command returns False for empty string."""
        router = CommandRouter()
        assert router.is_command("") is False


class TestCommandRouterParseCommand:
    """Tests for parse_command method."""

    def test_parse_model_command(self):
        """Test parsing /model command."""
        router = CommandRouter()
        result = router.parse_command("/model coder")
        assert result is not None
        assert result.command == "model"
        assert result.args == ["coder"]
        assert result.raw == "/model coder"

    def test_parse_reset_command(self):
        """Test parsing /reset command."""
        router = CommandRouter()
        result = router.parse_command("/reset")
        assert result is not None
        assert result.command == "reset"
        assert result.args == []

    def test_parse_help_command(self):
        """Test parsing /help command."""
        router = CommandRouter()
        result = router.parse_command("/help")
        assert result is not None
        assert result.command == "help"
        assert result.args == []

    def test_parse_clear_command(self):
        """Test parsing /clear command."""
        router = CommandRouter()
        result = router.parse_command("/clear")
        assert result is not None
        assert result.command == "clear"
        assert result.args == []

    def test_parse_command_with_quoted_args(self):
        """Test parsing command with quoted arguments."""
        router = CommandRouter()
        result = router.parse_command('/model "my agent"')
        assert result is not None
        assert result.command == "model"
        assert result.args == ["my agent"]

    def test_parse_command_with_multiple_quoted_args(self):
        """Test parsing command with multiple quoted arguments."""
        router = CommandRouter()
        result = router.parse_command('/model "agent one" "agent two"')
        assert result is not None
        assert result.command == "model"
        assert result.args == ["agent one", "agent two"]

    def test_parse_command_case_insensitive(self):
        """Test case-insensitive command parsing."""
        router = CommandRouter()
        result = router.parse_command("/MODEL coder")
        assert result is not None
        assert result.command == "model"
        assert result.args == ["coder"]

        result = router.parse_command("/Reset")
        assert result is not None
        assert result.command == "reset"

    def test_parse_command_with_extra_spaces(self):
        """Test parsing command with extra spaces."""
        router = CommandRouter()
        result = router.parse_command("  /model   coder  ")
        assert result is not None
        assert result.command == "model"
        assert result.args == ["coder"]

    def test_parse_non_command(self):
        """Test parsing non-command text returns None."""
        router = CommandRouter()
        result = router.parse_command("hello world")
        assert result is None

    def test_parse_empty_string(self):
        """Test parsing empty string returns None."""
        router = CommandRouter()
        result = router.parse_command("")
        assert result is None

    def test_parse_only_slash(self):
        """Test parsing just '/' returns None."""
        router = CommandRouter()
        result = router.parse_command("/")
        assert result is None


class TestCommandRouterExecute:
    """Tests for execute method."""

    def test_execute_model_command(self):
        """Test executing /model command."""
        router = CommandRouter()
        result = router.execute("model", ["coder"])
        assert "coder" in result

    def test_execute_reset_command(self):
        """Test executing /reset command."""
        router = CommandRouter()
        result = router.execute("reset", [])
        assert "reset" in result.lower()

    def test_execute_help_command(self):
        """Test executing /help command."""
        router = CommandRouter()
        result = router.execute("help", [])
        assert "model" in result
        assert "reset" in result
        assert "help" in result
        assert "clear" in result

    def test_execute_clear_command(self):
        """Test executing /clear command."""
        router = CommandRouter()
        result = router.execute("clear", [])
        assert "cleared" in result.lower() or "clear" in result.lower()

    def test_execute_unknown_command(self):
        """Test executing unknown command returns error."""
        router = CommandRouter()
        result = router.execute("unknown", [])
        assert "Unknown command" in result


class TestCommandRouterRegisterHandler:
    """Tests for register_handler method."""

    def test_register_custom_handler(self):
        """Test registering a custom command handler."""
        router = CommandRouter()

        def custom_handler(args: list[str]) -> str:
            return f"Custom: {', '.join(args)}"

        router.register_handler("custom", custom_handler)
        result = router.execute("custom", ["arg1", "arg2"])
        assert "Custom: arg1, arg2" == result

    def test_register_handler_case_insensitive(self):
        """Test that custom handlers are case-insensitive."""
        router = CommandRouter()

        def custom_handler(_args: list[str]) -> str:
            return "Custom called"

        router.register_handler("Custom", custom_handler)
        result = router.execute("custom", [])
        assert "Custom called" == result


class TestCommandRouterQAScenarios:
    """Test QA scenarios from requirements."""

    def test_qa_scenario_1(self):
        """Test from QA scenarios."""
        router = CommandRouter()
        result = router.parse_command("/model coder")
        assert result is not None
        assert result.command == "model"
        assert result.args == ["coder"]

    def test_qa_scenario_2(self):
        """Test from QA scenarios - non-command returns None."""
        router = CommandRouter()
        result = router.parse_command("hello world")
        assert result is None
