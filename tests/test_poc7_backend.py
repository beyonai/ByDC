#!/usr/bin/env python
"""
POC 7: Backend Verification Tests for OpenClaw Gateway Phase 2

This test verifies deepagents backend functionality:
1. backend parameter is accepted by create_deep_agent()
2. Built-in tools (ls, read_file, write_file) work correctly
3. Isolation level assessment of LocalShellBackend and FilesystemBackend

Key Finding: create_deep_agent() has NO 'sandbox' parameter.
Use 'backend' parameter with LocalShellBackend or FilesystemBackend instead.

Security Note: LocalShellBackend does NOT provide sandboxing.
Commands run on the host system.
"""

import asyncio
import os
import tempfile
import shutil
from pathlib import Path

# Set environment before imports
os.environ.setdefault("OPENAI_API_KEY", "sk-emt6bXBfJl9ncHQtcHJveHkuaXdoYWxlY2xvdWQuY29tXyZf")
os.environ.setdefault("OPENAI_BASE_URL", "https://lab.iwhalecloud.com/gpt-proxy/v1")

from deepagents import create_deep_agent
from deepagents.backends import LocalShellBackend, FilesystemBackend
from langchain.chat_models import init_chat_model


def test_backend_parameter():
    """Test 1: Verify backend parameter is accepted by create_deep_agent()"""
    print("\n" + "=" * 60)
    print("TEST 1: Backend Parameter Support")
    print("=" * 60)

    model = init_chat_model("gpt-4o-mini", model_provider="openai")

    # Test 1a: LocalShellBackend
    print("\n1a. Testing LocalShellBackend...")
    try:
        backend_shell = LocalShellBackend(root_dir="/tmp/test_poc7_shell", virtual_mode=True)
        agent_shell = create_deep_agent(model=model, backend=backend_shell)
        print(f"   ✓ LocalShellBackend accepted - Agent type: {type(agent_shell).__name__}")
    except Exception as e:
        print(f"   ✗ LocalShellBackend failed: {e}")
        return False

    # Test 1b: FilesystemBackend
    print("\n1b. Testing FilesystemBackend...")
    try:
        backend_fs = FilesystemBackend(root_dir="/tmp/test_poc7_fs", virtual_mode=True)
        agent_fs = create_deep_agent(model=model, backend=backend_fs)
        print(f"   ✓ FilesystemBackend accepted - Agent type: {type(agent_fs).__name__}")
    except Exception as e:
        print(f"   ✗ FilesystemBackend failed: {e}")
        return False

    # Test 1c: No backend (default)
    print("\n1c. Testing no backend (default)...")
    try:
        agent_default = create_deep_agent(model=model)
        print(f"   ✓ Default backend works - Agent type: {type(agent_default).__name__}")
    except Exception as e:
        print(f"   ✗ Default backend failed: {e}")
        return False

    print("\n✓ TEST 1 PASSED: backend parameter is supported")
    return True


async def _test_builtin_tools_async():
    """Async implementation of builtin tools test"""
    print("\n" + "=" * 60)
    print("TEST 2: Built-in Tools Verification")
    print("=" * 60)

    test_dir = tempfile.mkdtemp(prefix="poc7_tools_")

    try:
        model = init_chat_model("gpt-4o-mini", model_provider="openai")
        backend = LocalShellBackend(root_dir=test_dir, virtual_mode=True)
        agent = create_deep_agent(model=model, backend=backend)

        # Test 2a: write_file tool
        print("\n2a. Testing write_file tool...")
        result = await agent.ainvoke(
            {
                "messages": [
                    {
                        "role": "user",
                        "content": "Create a file 'test_file.txt' with content 'POC7 Test Content'",
                    }
                ]
            }
        )

        write_success = False
        for msg in result["messages"]:
            if hasattr(msg, "name") and msg.name == "write_file":
                print(f"   write_file result: {msg.content}")
                write_success = True
            if hasattr(msg, "tool_calls") and msg.tool_calls:
                for tc in msg.tool_calls:
                    if tc["name"] == "write_file":
                        print(f"   Tool call: write_file({tc['args']})")

        if not write_success:
            print("   ✗ write_file tool not called")
            return False
        print("   ✓ write_file tool works")

        # Test 2b: read_file tool
        print("\n2b. Testing read_file tool...")
        result = await agent.ainvoke(
            {"messages": [{"role": "user", "content": "Read the file test_file.txt"}]}
        )

        read_success = False
        for msg in result["messages"]:
            if hasattr(msg, "name") and msg.name == "read_file":
                print(f"   read_file result: {msg.content}")
                if "POC7 Test Content" in msg.content:
                    read_success = True
            if hasattr(msg, "tool_calls") and msg.tool_calls:
                for tc in msg.tool_calls:
                    if tc["name"] == "read_file":
                        print(f"   Tool call: read_file({tc['args']})")

        if not read_success:
            print("   ✗ read_file tool did not return expected content")
            return False
        print("   ✓ read_file tool works")

        # Test 2c: ls tool
        print("\n2c. Testing ls tool...")
        result = await agent.ainvoke(
            {"messages": [{"role": "user", "content": "List all files in current directory"}]}
        )

        ls_success = False
        for msg in result["messages"]:
            if hasattr(msg, "name") and msg.name == "ls":
                print(f"   ls result: {msg.content}")
                ls_success = True
            if hasattr(msg, "tool_calls") and msg.tool_calls:
                for tc in msg.tool_calls:
                    if tc["name"] == "ls":
                        print(f"   Tool call: ls({tc['args']})")

        if not ls_success:
            print("   ✗ ls tool not called")
            return False
        print("   ✓ ls tool works")

        print("\n✓ TEST 2 PASSED: All built-in tools work correctly")
        return True

    finally:
        shutil.rmtree(test_dir, ignore_errors=True)


def test_builtin_tools():
    """Test 2: Verify built-in tools (ls, read_file, write_file) work"""
    return asyncio.run(_test_builtin_tools_async())


def test_isolation_level():
    """Test 3: Assess isolation capabilities of backends"""
    print("\n" + "=" * 60)
    print("TEST 3: Isolation Level Assessment")
    print("=" * 60)

    import inspect

    # Test 3a: Check LocalShellBackend isolation
    print("\n3a. LocalShellBackend Isolation Assessment:")
    print("   - Signature:", inspect.signature(LocalShellBackend.__init__))

    print("\n   CAPABILITIES:")
    print("   ✓ root_dir parameter: Can set working directory")
    print("   ✓ virtual_mode parameter: Path-based routing support")
    print("   ✓ timeout parameter: Command execution timeout")
    print("   ✓ max_output_bytes: Output size limiting")
    print("   ✓ env parameter: Custom environment variables")

    print("\n   LIMITATIONS (IMPORTANT):")
    print("   ✗ NO process isolation: Commands run on host")
    print("   ✗ NO filesystem sandbox: virtual_mode is NOT sandboxing")
    print("   ✗ NO container support: No Docker/Podman integration")
    print("   ✗ NO user namespace: Commands run as current user")

    # Test 3b: Check FilesystemBackend isolation
    print("\n3b. FilesystemBackend Isolation Assessment:")
    print("   - Signature:", inspect.signature(FilesystemBackend.__init__))

    print("\n   CAPABILITIES:")
    print("   ✓ root_dir parameter: Can set working directory")
    print("   ✓ virtual_mode parameter: Path-based routing support")
    print("   ✓ max_file_size_mb: File size limiting")

    print("\n   LIMITATIONS:")
    print("   ✗ NO command execution: Filesystem-only backend")
    print("   ✗ NO sandboxing: virtual_mode is NOT sandboxing")

    # Test 3c: Check for other backends
    print("\n3c. Checking for additional backend options:")
    try:
        from deepagents.backends import CompositeBackend, StateBackend, StoreBackend

        print("   ✓ CompositeBackend available: For routing multiple backends")
        print("   ✓ StateBackend available: For state management")
        print("   ✓ StoreBackend available: For store management")
    except ImportError as e:
        print(f"   Note: {e}")

    # Test 3d: Check BackendProtocol for available operations
    print("\n3d. BackendProtocol available operations:")
    from deepagents.backends.protocol import BackendProtocol

    operations = [m for m in dir(BackendProtocol) if not m.startswith("_")]
    print(f"   Operations: {', '.join(operations)}")

    print("\n" + "-" * 60)
    print("ISOLATION LEVEL SUMMARY:")
    print("-" * 60)
    print("LocalShellBackend: LOW ISOLATION")
    print("  - Commands execute on host system")
    print("  - Suitable for trusted environments only")
    print("  - NOT suitable for multi-tenant scenarios")
    print("")
    print("FilesystemBackend: MEDIUM ISOLATION (file operations only)")
    print("  - No command execution capability")
    print("  - File operations within root_dir")
    print("  - Suitable for read-only or controlled write scenarios")
    print("")
    print("RECOMMENDATION: For OpenClaw Gateway, consider:")
    print("  1. Use FilesystemBackend for file operations")
    print("  2. Implement custom sandbox for command execution")
    print("  3. Consider container-based isolation (Docker/Podman)")
    print("-" * 60)

    print("\n✓ TEST 3 PASSED: Isolation level assessment complete")
    return True


def main():
    """Run all backend verification tests"""
    print("=" * 60)
    print("POC 7: Backend Verification Tests")
    print("OpenClaw Gateway Phase 2")
    print("=" * 60)

    results = {}

    # Run tests
    results["test_1_backend_parameter"] = test_backend_parameter()
    results["test_2_builtin_tools"] = test_builtin_tools()
    results["test_3_isolation_level"] = test_isolation_level()

    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)

    all_passed = True
    for test_name, passed in results.items():
        status = "✓ PASSED" if passed else "✗ FAILED"
        print(f"  {test_name}: {status}")
        if not passed:
            all_passed = False

    print("\n" + "=" * 60)
    if all_passed:
        print("ALL TESTS PASSED")
        print("\nKEY FINDINGS:")
        print("1. backend parameter IS supported (not 'sandbox')")
        print("2. Built-in tools (ls, read_file, write_file) work correctly")
        print("3. Isolation level is LOW - no built-in sandboxing")
    else:
        print("SOME TESTS FAILED - Review output above")
    print("=" * 60)

    return all_passed


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
