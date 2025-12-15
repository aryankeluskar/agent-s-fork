"""
Executor that converts pyautogui code strings to robotgo JSON commands and executes them.
"""
import re
import json
import platform
import subprocess
import logging
from pathlib import Path
from typing import Dict, Any, Optional

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


def parse_pyautogui_code(code: str) -> list:
    """
    Parse pyautogui code string into a list of action dictionaries.
    
    Args:
        code: Python code string with pyautogui calls
    
    Returns:
        List of action dictionaries ready for JSON serialization
    """
    actions = []
    platform_name = platform.system().lower()
    
    # Split by semicolons and process each statement
    statements = [s.strip() for s in code.split(';') if s.strip() and not s.strip().startswith('#')]
    
    for stmt in statements:
        if 'import' in stmt:
            continue  # Skip import statements
        
        # Parse pyautogui.click(x, y, clicks=1, button='left')
        click_match = re.search(r'pyautogui\.click\(([^)]+)\)', stmt)
        if click_match:
            args_str = click_match.group(1)
            # Extract x, y, clicks, button
            x_match = re.search(r'(\d+)\s*,', args_str)
            y_match = re.search(r',\s*(\d+)', args_str)
            clicks_match = re.search(r'clicks\s*=\s*(\d+)', args_str)
            button_match = re.search(r"button\s*=\s*['\"]([^'\"]+)['\"]", args_str)
            
            params = {}
            if x_match and y_match:
                params['x'] = int(x_match.group(1))
                params['y'] = int(y_match.group(1))
            if clicks_match:
                params['clicks'] = int(clicks_match.group(1))
            if button_match:
                params['button'] = button_match.group(1)
            
            # Check for keyDown/keyUp before click
            hold_keys = []
            if 'keyDown' in code[:code.index(stmt)]:
                # Extract held keys (simplified - would need more parsing)
                pass
            
            actions.append({
                'type': 'click',
                'params': params,
                'platform': platform_name
            })
            continue
        
        # Parse pyautogui.moveTo(x, y)
        moveto_match = re.search(r'pyautogui\.moveTo\(([^)]+)\)', stmt)
        if moveto_match:
            args_str = moveto_match.group(1)
            coords = [int(x.strip()) for x in args_str.split(',')[:2]]
            if len(coords) == 2:
                actions.append({
                    'type': 'moveTo',
                    'params': {'x': coords[0], 'y': coords[1]},
                    'platform': platform_name
                })
            continue
        
        # Parse pyautogui.dragTo(x, y, duration=1., button='left')
        drag_match = re.search(r'pyautogui\.dragTo\(([^)]+)\)', stmt)
        if drag_match:
            args_str = drag_match.group(1)
            coords = [int(x.strip()) for x in args_str.split(',')[:2]]
            button_match = re.search(r"button\s*=\s*['\"]([^'\"]+)['\"]", args_str)
            button = button_match.group(1) if button_match else 'left'
            
            # Need to get start position from previous moveTo
            if actions and actions[-1]['type'] == 'moveTo':
                start_params = actions[-1]['params']
                actions.pop()  # Remove the moveTo
                actions.append({
                    'type': 'dragTo',
                    'params': {
                        'x1': start_params['x'],
                        'y1': start_params['y'],
                        'x2': coords[0],
                        'y2': coords[1],
                        'button': button
                    },
                    'platform': platform_name
                })
            continue
        
        # Parse pyautogui.write(text) or pyautogui.typewrite(text)
        write_match = re.search(r'pyautogui\.(?:write|typewrite)\(([^)]+)\)', stmt)
        if write_match:
            text_str = write_match.group(1)
            # Try to extract string value
            text_match = re.search(r"['\"]([^'\"]+)['\"]", text_str)
            if text_match:
                actions.append({
                    'type': 'type',
                    'params': {'text': text_match.group(1)},
                    'platform': platform_name
                })
            continue
        
        # Parse pyautogui.press('key')
        press_match = re.search(r"pyautogui\.press\(['\"]([^'\"]+)['\"]\)", stmt)
        if press_match:
            key = press_match.group(1)
            actions.append({
                'type': 'press',
                'params': {'key': key},
                'platform': platform_name
            })
            continue
        
        # Parse pyautogui.hotkey('key1', 'key2', ...)
        hotkey_match = re.search(r'pyautogui\.hotkey\(([^)]+)\)', stmt)
        if hotkey_match:
            args_str = hotkey_match.group(1)
            keys = re.findall(r"['\"]([^'\"]+)['\"]", args_str)
            if keys:
                actions.append({
                    'type': 'hotkey',
                    'params': {'keys': keys},
                    'platform': platform_name
                })
            continue
        
        # Parse pyautogui.keyDown('key') and pyautogui.keyUp('key')
        keydown_match = re.search(r"pyautogui\.keyDown\(['\"]([^'\"]+)['\"]\)", stmt)
        if keydown_match:
            actions.append({
                'type': 'keyDown',
                'params': {'key': keydown_match.group(1)},
                'platform': platform_name
            })
            continue
        
        keyup_match = re.search(r"pyautogui\.keyUp\(['\"]([^'\"]+)['\"]\)", stmt)
        if keyup_match:
            actions.append({
                'type': 'keyUp',
                'params': {'key': keyup_match.group(1)},
                'platform': platform_name
            })
            continue
        
        # Parse pyautogui.vscroll(clicks) or pyautogui.hscroll(clicks)
        vscroll_match = re.search(r'pyautogui\.vscroll\(([^)]+)\)', stmt)
        if vscroll_match:
            clicks = int(vscroll_match.group(1))
            # Get position from previous moveTo if available
            x, y = 0, 0
            if actions and actions[-1]['type'] == 'moveTo':
                x = actions[-1]['params']['x']
                y = actions[-1]['params']['y']
            actions.append({
                'type': 'scroll',
                'params': {'x': x, 'y': y, 'clicks': clicks, 'horizontal': False},
                'platform': platform_name
            })
            continue
        
        hscroll_match = re.search(r'pyautogui\.hscroll\(([^)]+)\)', stmt)
        if hscroll_match:
            clicks = int(hscroll_match.group(1))
            x, y = 0, 0
            if actions and actions[-1]['type'] == 'moveTo':
                x = actions[-1]['params']['x']
                y = actions[-1]['params']['y']
            actions.append({
                'type': 'scroll',
                'params': {'x': x, 'y': y, 'clicks': clicks, 'horizontal': True},
                'platform': platform_name
            })
            continue
        
        # Parse time.sleep(seconds)
        sleep_match = re.search(r'time\.sleep\(([^)]+)\)', stmt)
        if sleep_match:
            duration = float(sleep_match.group(1))
            actions.append({
                'type': 'wait',
                'params': {'duration': duration},
                'platform': platform_name
            })
            continue
    
    return actions


def execute_robotgo_code(code: str) -> bool:
    """
    Execute pyautogui code by converting it to robotgo JSON commands.
    
    Args:
        code: Python code string with pyautogui calls
    
    Returns:
        True if all actions succeeded, False otherwise
    """
    try:
        actions = parse_pyautogui_code(code)
        executor_path = get_robotgo_executor_path()
        
        for action in actions:
            json_input = json.dumps(action)
            
            result = subprocess.run(
                [executor_path, "-json", json_input],
                capture_output=True,
                text=True,
                timeout=10.0
            )
            
            if result.returncode != 0:
                logger.error(f"robotgo_executor failed for action {action['type']}: {result.stderr}")
                return False
        
        return True
    except Exception as e:
        logger.error(f"Error executing robotgo code: {e}")
        return False


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

