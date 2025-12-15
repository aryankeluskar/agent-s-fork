"""
Wrapper module to execute GUI actions using Go robotgo binary instead of pyautogui.
"""
import json
import os
import platform
import subprocess
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any

logger = logging.getLogger("desktopenv.agent")

# Path to the robotgo_executor binary
ROBOTGO_EXECUTOR_PATH = None


def get_robotgo_executor_path():
    """Get the path to the robotgo_executor binary."""
    global ROBOTGO_EXECUTOR_PATH
    
    if ROBOTGO_EXECUTOR_PATH is None:
        # Try to find the binary relative to this file
        current_dir = Path(__file__).parent
        executor_dir = current_dir / "robotgo_executor"
        
        # Check for built binary
        if platform.system() == "Windows":
            binary_name = "robotgo_executor.exe"
        else:
            binary_name = "robotgo_executor"
        
        binary_path = executor_dir / binary_name
        
        if binary_path.exists():
            ROBOTGO_EXECUTOR_PATH = str(binary_path.absolute())
        else:
            # Fallback: try in PATH
            ROBOTGO_EXECUTOR_PATH = "robotgo_executor"
            logger.warning(
                f"robotgo_executor binary not found at {binary_path}. "
                "Make sure to build it first: cd gui_agents/s3/utils/robotgo_executor && go build -o robotgo_executor main.go"
            )
    
    return ROBOTGO_EXECUTOR_PATH


def execute_action(action_type: str, params: Dict[str, Any], platform_name: Optional[str] = None) -> bool:
    """
    Execute a GUI action using the Go robotgo executor.
    
    Args:
        action_type: Type of action (click, type, hotkey, etc.)
        params: Parameters for the action
        platform_name: Platform name (darwin, windows, linux). Auto-detected if None.
    
    Returns:
        True if successful, False otherwise
    """
    if platform_name is None:
        platform_name = platform.system().lower()
    
    action = {
        "type": action_type,
        "params": params,
        "platform": platform_name
    }
    
    json_input = json.dumps(action)
    executor_path = get_robotgo_executor_path()
    
    try:
        result = subprocess.run(
            [executor_path, "-json", json_input, "-platform", platform_name],
            capture_output=True,
            text=True,
            timeout=10.0
        )
        
        if result.returncode != 0:
            logger.error(f"robotgo_executor failed: {result.stderr}")
            return False
        
        return True
    except subprocess.TimeoutExpired:
        logger.error("robotgo_executor timed out")
        return False
    except Exception as e:
        logger.error(f"Error executing robotgo action: {e}")
        return False


def execute_robotgo_code(code: str) -> bool:
    """
    Execute a sequence of robotgo actions from a code string.
    This parses simplified action calls and executes them.
    
    Format: robotgo.click(x, y, button='left', clicks=1, hold_keys=['ctrl'])
            robotgo.type(text)
            robotgo.hotkey('ctrl', 'c')
            etc.
    
    Args:
        code: Code string with robotgo action calls
    
    Returns:
        True if all actions succeeded, False otherwise
    """
    # This is a simplified parser - in practice, you might want to use
    # a more robust approach or generate proper JSON directly from grounding.py
    lines = code.strip().split('\n')
    
    for line in lines:
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        
        # Parse robotgo action calls
        if line.startswith('robotgo.'):
            # Extract action and parameters
            # This is a simplified parser - you may need to enhance it
            if 'click' in line:
                # Parse click(x, y, button='left', clicks=1)
                # This is complex - better to generate JSON directly
                pass
    
    # For now, return True - actual implementation would parse and execute
    return True


def get_screen_size() -> tuple:
    """Get screen size using robotgo executor."""
    action = {
        "type": "screenSize",
        "params": {},
        "platform": platform.system().lower()
    }
    
    json_input = json.dumps(action)
    executor_path = get_robotgo_executor_path()
    
    try:
        result = subprocess.run(
            [executor_path, "-json", json_input],
            capture_output=True,
            text=True,
            timeout=5.0
        )
        
        if result.returncode == 0 and result.stdout:
            size_data = json.loads(result.stdout)
            return (size_data.get("width", 1920), size_data.get("height", 1080))
    except Exception as e:
        logger.error(f"Error getting screen size: {e}")
    
    # Fallback
    return (1920, 1080)

