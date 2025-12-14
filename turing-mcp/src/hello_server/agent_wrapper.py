"""
Agent-S wrapper for subprocess execution with progress reporting.
"""

import io
import logging
import os
import platform
import sys
import time
from typing import Dict, Any, Optional
from PIL import Image

# Import Agent-S components
try:
    import pyautogui
    from gui_agents.s3.agents.grounding import OSWorldACI
    from gui_agents.s3.agents.agent_s import AgentS3
    from gui_agents.s3.utils.local_env import LocalEnv
except ImportError as e:
    print(f"Warning: Failed to import Agent-S dependencies: {e}")
    print("Make sure Agent-S is installed in the Python path")

from .models import ConfigSchema
from .task_manager import TaskManager


logger = logging.getLogger(__name__)


def scale_screen_dimensions(width: int, height: int, max_dim_size: int):
    """Scale screen dimensions to fit within max_dim_size while preserving aspect ratio."""
    scale_factor = min(max_dim_size / width, max_dim_size / height, 1)
    safe_width = int(width * scale_factor)
    safe_height = int(height * scale_factor)
    return safe_width, safe_height


class AgentWrapper:
    """
    Wrapper for Agent-S execution with progress tracking.
    
    This class handles:
    - Agent initialization from config
    - Grounding model validation
    - Task execution with screenshot capture
    - Progress reporting
    - Error handling
    """
    
    def __init__(self, config: ConfigSchema, task_manager: TaskManager):
        """
        Initialize Agent wrapper.
        
        Args:
            config: Configuration schema
            task_manager: Task manager instance
        """
        self.config = config
        self.task_manager = task_manager
        self.agent = None
        self.grounding_agent = None
        self.scaled_width = None
        self.scaled_height = None
        self.screen_width = None
        self.screen_height = None
        
        # Initialize logging
        logging.basicConfig(level=logging.INFO)
    
    def initialize_agent(self) -> bool:
        """
        Initialize Agent-S and grounding model.
        
        Returns:
            True if successful, False otherwise
        """
        try:
            logger.info("🔧 Initializing Agent-S...")
            
            # Get screen dimensions
            self.screen_width, self.screen_height = pyautogui.size()
            
            # Scale screenshot size to ensure it fits in UI-TARS context limit
            self.scaled_width, self.scaled_height = scale_screen_dimensions(
                self.screen_width, self.screen_height, max_dim_size=2400
            )
            
            logger.info(f"📐 Screen size: {self.screen_width}x{self.screen_height}")
            logger.info(f"📸 Screenshot size: {self.scaled_width}x{self.scaled_height}")
            logger.info(f"🎯 Grounding model config: {self.config.grounding_width}x{self.config.grounding_height}")
            
            # Configure engine parameters
            engine_params = {
                "engine_type": self.config.model_provider,
                "model": self.config.model_name,
                "api_key": self.config.model_api_key,
                "base_url": self.config.model_url,
                "temperature": self.config.model_temperature,
            }
            
            # Configure grounding engine
            grounding_params = {
                "engine_type": self.config.ground_provider,
                "model": self.config.ground_model,
                "base_url": self.config.ground_url,
                "api_key": self.config.ground_api_key,
                "grounding_width": self.config.grounding_width,
                "grounding_height": self.config.grounding_height,
            }
            
            # Initialize local environment if enabled
            local_env = None
            if self.config.enable_local_env:
                logger.warning("⚠️  Local coding environment enabled. This will execute arbitrary code locally!")
                local_env = LocalEnv()
            
            # Initialize grounding agent
            current_platform = platform.system().lower()
            self.grounding_agent = OSWorldACI(
                env=local_env,
                platform=current_platform,
                engine_params_for_generation=engine_params,
                engine_params_for_grounding=grounding_params,
                width=self.screen_width,
                height=self.screen_height,
            )
            
            # Validate grounding model connectivity
            logger.info("📡 Testing grounding model connectivity...")
            test_screenshot = pyautogui.screenshot()
            test_screenshot = test_screenshot.resize((self.scaled_width, self.scaled_height), Image.LANCZOS)
            buffered = io.BytesIO()
            test_screenshot.save(buffered, format="PNG")
            test_screenshot_bytes = buffered.getvalue()
            
            self.grounding_agent.validate_grounding_model(test_screenshot_bytes)
            logger.info("✅ Grounding model ready!")
            
            # Initialize main agent
            self.agent = AgentS3(
                worker_engine_params=engine_params,
                grounding_agent=self.grounding_agent,
                platform=current_platform,
                max_trajectory_length=self.config.max_trajectory_length,
                enable_reflection=self.config.enable_reflection,
            )
            
            logger.info("✅ Agent-S initialized successfully!")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize Agent-S: {e}")
            logger.exception(e)
            return False
    
    def execute_task(
        self,
        task_id: str,
        instruction: str,
        progress_callback: Optional[callable] = None
    ) -> Dict[str, Any]:
        """
        Execute a task with the agent.
        
        Args:
            task_id: Task identifier
            instruction: Task instruction
            progress_callback: Optional callback for progress updates (step, max_steps, message)
            
        Returns:
            Dict with execution result
        """
        try:
            # Initialize agent if not already done
            if self.agent is None:
                if not self.initialize_agent():
                    return {
                        "success": False,
                        "error": "Failed to initialize Agent-S"
                    }
            
            # Reset agent state
            self.agent.reset()
            
            # Set task instruction for code agent
            if hasattr(self.grounding_agent, 'set_task_instruction'):
                self.grounding_agent.set_task_instruction(instruction)
            
            logger.info(f"🚀 Starting task execution: {instruction}")
            
            # Main execution loop
            obs = {}
            for step in range(self.config.max_steps):
                try:
                    logger.info(f"🔄 Step {step + 1}/{self.config.max_steps}")
                    
                    # Capture screenshot
                    screenshot = pyautogui.screenshot()
                    screenshot = screenshot.resize((self.scaled_width, self.scaled_height), Image.LANCZOS)
                    
                    # Convert to bytes
                    buffered = io.BytesIO()
                    screenshot.save(buffered, format="PNG")
                    screenshot_bytes = buffered.getvalue()
                    obs["screenshot"] = screenshot_bytes
                    
                    # Get next action from agent
                    info, code = self.agent.predict(instruction=instruction, observation=obs)
                    
                    # Extract plan and reflection
                    plan = info.get("executor_plan", "")
                    reflection = info.get("reflection", "")
                    action_code = code[0] if code else ""
                    
                    logger.info(f"📋 Plan: {plan[:100]}...")
                    logger.info(f"💻 Code: {action_code[:100]}...")
                    
                    # Update task state
                    self.task_manager.update_step(
                        task_id=task_id,
                        step_number=step,
                        plan=plan,
                        reflection=reflection,
                        code=action_code,
                        screenshot=screenshot_bytes
                    )
                    
                    # Report progress
                    if progress_callback:
                        progress_callback(step + 1, self.config.max_steps, plan)
                    
                    # Check for completion
                    if "done" in action_code.lower():
                        logger.info("✅ Task completed successfully!")
                        self.task_manager.mark_complete(task_id, "success")
                        return {
                            "success": True,
                            "message": "Task completed",
                            "steps": step + 1
                        }
                    
                    # Check for failure
                    if "fail" in action_code.lower():
                        logger.warning("⚠️ Agent marked task as failed")
                        self.task_manager.mark_complete(task_id, "failed", "Agent marked task as impossible")
                        return {
                            "success": False,
                            "error": "Agent marked task as impossible",
                            "steps": step + 1
                        }
                    
                    # Check for wait/next
                    if "wait" in action_code.lower():
                        logger.info("⏳ Agent requested wait...")
                        time.sleep(5)
                        continue
                    
                    if "next" in action_code.lower():
                        logger.info("⏭️ Agent requested next step...")
                        continue
                    
                    # Execute the action
                    logger.info(f"⚡ Executing: {action_code[:200]}...")
                    time.sleep(1.0)
                    
                    try:
                        exec(action_code)
                        time.sleep(1.0)
                    except Exception as exec_error:
                        logger.error(f"❌ Execution error: {exec_error}")
                        # Log error but continue - some errors are recoverable
                        self.task_manager.update_step(
                            task_id=task_id,
                            step_number=step,
                            error=str(exec_error)
                        )
                        time.sleep(2.0)
                
                except Exception as step_error:
                    logger.error(f"❌ Error in step {step}: {step_error}")
                    logger.exception(step_error)
                    
                    # Update task with error
                    self.task_manager.update_step(
                        task_id=task_id,
                        step_number=step,
                        error=str(step_error)
                    )
                    
                    # Continue to next step (some errors are recoverable)
                    time.sleep(2.0)
                    continue
            
            # Reached max steps
            logger.warning(f"⚠️ Reached maximum steps ({self.config.max_steps})")
            self.task_manager.mark_complete(
                task_id,
                "completed",
                f"Reached maximum steps ({self.config.max_steps})"
            )
            
            return {
                "success": True,
                "message": f"Completed {self.config.max_steps} steps",
                "steps": self.config.max_steps
            }
            
        except Exception as e:
            logger.error(f"❌ Task execution failed: {e}")
            logger.exception(e)
            
            self.task_manager.mark_complete(task_id, "failed", str(e))
            
            return {
                "success": False,
                "error": str(e)
            }


def run_task_subprocess(
    config_dict: Dict[str, Any],
    task_id: str,
    instruction: str,
    task_manager: TaskManager
) -> Dict[str, Any]:
    """
    Run a task in a subprocess (for isolation).
    
    Args:
        config_dict: Configuration dictionary
        task_id: Task identifier
        instruction: Task instruction
        task_manager: TaskManager instance
        
    Returns:
        Execution result dictionary
    """
    try:
        # Reconstruct config
        config = ConfigSchema(**config_dict)
        
        # Create wrapper and execute
        wrapper = AgentWrapper(config, task_manager)
        result = wrapper.execute_task(task_id, instruction)
        
        return result
        
    except Exception as e:
        logger.error(f"❌ Subprocess execution failed: {e}")
        return {
            "success": False,
            "error": str(e)
        }
