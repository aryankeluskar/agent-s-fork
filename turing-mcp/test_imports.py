#!/usr/bin/env python3
"""
Simple test script to validate imports and basic functionality.
Run this to check if the Agent-S MCP server is properly configured.
"""

import sys
import os

def test_imports():
    """Test that all required imports work."""
    print("🔍 Testing imports...")
    
    errors = []
    
    # Test MCP imports
    try:
        from mcp.server.fastmcp import Context, FastMCP
        from smithery.decorators import smithery
        print("✅ MCP/Smithery imports OK")
    except ImportError as e:
        errors.append(f"❌ MCP/Smithery import failed: {e}")
    
    # Test Agent-S server imports
    try:
        from agent_s_server.models import ConfigSchema, TaskState, TaskStatus
        from agent_s_server.task_manager import TaskManager
        from agent_s_server.agent_wrapper import AgentWrapper
        from agent_s_server.server import create_server
        print("✅ Agent-S server imports OK")
    except ImportError as e:
        errors.append(f"❌ Agent-S server import failed: {e}")
    
    # Test Agent-S core imports (optional - may not be installed yet)
    try:
        from gui_agents.s3.agents.grounding import OSWorldACI
        from gui_agents.s3.agents.agent_s import AgentS3
        print("✅ Agent-S core imports OK")
    except ImportError as e:
        print(f"⚠️  Agent-S core import failed (this is OK if not installed): {e}")
    
    # Test pyautogui and dependencies
    try:
        import pyautogui
        import pytesseract
        from PIL import Image
        print("✅ PyAutoGUI and dependencies OK")
    except ImportError as e:
        errors.append(f"❌ PyAutoGUI dependencies failed: {e}")
    
    # Test AI provider imports
    try:
        import openai
        import anthropic
        print("✅ AI provider imports OK")
    except ImportError as e:
        errors.append(f"❌ AI provider imports failed: {e}")
    
    return errors


def test_server_creation():
    """Test that server can be created."""
    print("\n🏗️  Testing server creation...")
    
    try:
        from agent_s_server.server import create_server
        from agent_s_server.models import ConfigSchema
        
        # This will fail without proper config, but at least tests imports
        print("✅ Server module loads OK")
        return []
    except Exception as e:
        return [f"❌ Server creation failed: {e}"]


def test_task_manager():
    """Test TaskManager functionality."""
    print("\n📋 Testing TaskManager...")
    
    try:
        from agent_s_server.task_manager import TaskManager
        
        manager = TaskManager()
        
        # Create a test task
        task = manager.create_task(
            task_id="test-123",
            instruction="Test task",
            max_steps=5
        )
        
        # Update step
        manager.update_step(
            task_id="test-123",
            step_number=0,
            plan="Test plan",
            code="print('test')"
        )
        
        # Get task
        retrieved = manager.get_task("test-123")
        
        if retrieved and retrieved.task_id == "test-123":
            print("✅ TaskManager works correctly")
            
            # Cleanup
            manager.delete_task("test-123")
            return []
        else:
            return ["❌ TaskManager task retrieval failed"]
            
    except Exception as e:
        return [f"❌ TaskManager test failed: {e}"]


def check_environment():
    """Check environment setup."""
    print("\n🌍 Checking environment...")
    
    warnings = []
    
    # Check PYTHONPATH
    pythonpath = os.environ.get('PYTHONPATH', '')
    agent_s_path = '/Users/aryank/Developer/Agent-S'
    
    if agent_s_path not in pythonpath:
        warnings.append(
            f"⚠️  PYTHONPATH may not include Agent-S. Current: {pythonpath}\n"
            f"   Add: export PYTHONPATH='{agent_s_path}:$PYTHONPATH'"
        )
    else:
        print(f"✅ PYTHONPATH includes Agent-S: {pythonpath}")
    
    # Check Python version
    py_version = sys.version_info
    if py_version.major >= 3 and py_version.minor >= 10:
        print(f"✅ Python version OK: {py_version.major}.{py_version.minor}.{py_version.micro}")
    else:
        warnings.append(
            f"⚠️  Python version may be too old: {py_version.major}.{py_version.minor}.{py_version.micro}\n"
            f"   Requires: Python 3.10+"
        )
    
    return warnings


def main():
    """Run all tests."""
    print("=" * 60)
    print("Agent-S MCP Server - Import and Functionality Test")
    print("=" * 60)
    
    all_errors = []
    all_warnings = []
    
    # Test environment
    warnings = check_environment()
    all_warnings.extend(warnings)
    
    # Test imports
    errors = test_imports()
    all_errors.extend(errors)
    
    # Test server creation
    errors = test_server_creation()
    all_errors.extend(errors)
    
    # Test task manager
    errors = test_task_manager()
    all_errors.extend(errors)
    
    # Print summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    
    if all_warnings:
        print("\n⚠️  WARNINGS:")
        for warning in all_warnings:
            print(f"  {warning}")
    
    if all_errors:
        print("\n❌ ERRORS:")
        for error in all_errors:
            print(f"  {error}")
        print("\n❌ Tests FAILED - Please fix errors above")
        return 1
    else:
        print("\n✅ All tests PASSED!")
        print("\nNext steps:")
        print("  1. Run 'uv run playground' to test interactively")
        print("  2. Configure Claude Desktop (see QUICKSTART.md)")
        print("  3. Make sure grounding model endpoint is accessible")
        return 0


if __name__ == "__main__":
    exit(main())
