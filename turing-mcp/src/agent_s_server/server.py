"""
Agent-S MCP Server

Provides tools and resources for controlling Agent-S GUI automation through MCP.
"""

import asyncio
import json
import logging
import threading
import time
import uuid
from typing import Optional

from mcp.server.fastmcp import Context, FastMCP
from smithery.decorators import smithery

from .models import (
    ConfigSchema,
    TaskResponse,
    TaskStatusResponse,
    TaskStatus
)
from .task_manager import TaskManager
from .agent_wrapper import AgentWrapper


# Initialize global task manager
task_manager = TaskManager(cleanup_age_hours=24)

# Lock for enforcing single-task execution
execution_lock = threading.Lock()

# Store agent wrapper per session (keyed by some session identifier)
# For now, we'll create it on-demand per task
agent_wrappers = {}

logger = logging.getLogger(__name__)


@smithery.server(config_schema=ConfigSchema)
def create_server():
    """Create and configure the Agent-S MCP server."""
    
    server = FastMCP("Agent-S GUI Automation")
    
    # ========== TOOLS ==========
    
    @server.tool()
    async def run_task(instruction: str, ctx: Context) -> str:
        """
        Execute a complete multi-step GUI automation task.
        
        This tool will:
        1. Initialize Agent-S with the configured models
        2. Execute the task step-by-step with automatic action execution
        3. Capture screenshots and report progress in real-time
        4. Return when task completes or reaches max steps
        
        Args:
            instruction: Natural language instruction for the GUI task
            ctx: MCP context (automatically provided)
            
        Returns:
            JSON string with task_id and initial status
            
        Example:
            instruction: "Open calculator and compute 123 + 456"
        """
        try:
            # Get session config
            config: ConfigSchema = ctx.session_config
            
            # Enforce single task limit (Phase 1)
            running_tasks = task_manager.get_running_tasks()
            if running_tasks:
                return json.dumps({
                    "error": "A task is already running",
                    "running_task_id": running_tasks[0],
                    "message": "Please wait for the current task to complete or cancel it first"
                })
            
            # Generate task ID
            task_id = str(uuid.uuid4())
            
            logger.info(f"📝 Creating task {task_id}: {instruction}")
            
            # Create task in manager
            task_manager.create_task(
                task_id=task_id,
                instruction=instruction,
                max_steps=config.max_steps
            )
            
            # Initialize agent wrapper
            wrapper = AgentWrapper(config, task_manager)
            
            # Validate grounding model before starting
            logger.info("🔍 Validating grounding model connectivity...")
            if not wrapper.initialize_agent():
                task_manager.mark_complete(task_id, "failed", "Failed to initialize Agent-S")
                return json.dumps({
                    "task_id": task_id,
                    "status": "failed",
                    "error": "Failed to initialize Agent-S. Check grounding model connectivity."
                })
            
            logger.info("✅ Grounding model validated!")
            
            # Define progress callback
            async def report_progress(step: int, max_steps: int, plan: str):
                """Report progress to MCP client."""
                try:
                    await ctx.report_progress(
                        progress=step,
                        total=max_steps,
                        description=f"Step {step}/{max_steps}: {plan[:100]}"
                    )
                except Exception as e:
                    logger.error(f"Failed to report progress: {e}")
            
            # Start task execution in background thread
            def execute_task():
                """Background execution function."""
                try:
                    # Create event loop for async progress reporting
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    
                    def sync_progress_callback(step, max_steps, plan):
                        """Sync wrapper for async progress reporting."""
                        try:
                            loop.run_until_complete(report_progress(step, max_steps, plan))
                        except Exception as e:
                            logger.error(f"Progress callback error: {e}")
                    
                    # Execute task
                    result = wrapper.execute_task(
                        task_id=task_id,
                        instruction=instruction,
                        progress_callback=sync_progress_callback
                    )
                    
                    logger.info(f"Task {task_id} completed: {result}")
                    
                except Exception as e:
                    logger.error(f"Task execution error: {e}")
                    logger.exception(e)
                    task_manager.mark_complete(task_id, "failed", str(e))
            
            # Start execution thread
            execution_thread = threading.Thread(target=execute_task, daemon=True)
            execution_thread.start()
            
            # Return immediately with task ID
            return json.dumps({
                "task_id": task_id,
                "status": "running",
                "message": f"Task started with {config.max_steps} max steps"
            })
            
        except Exception as e:
            logger.error(f"Failed to start task: {e}")
            logger.exception(e)
            return json.dumps({
                "error": str(e),
                "message": "Failed to start task"
            })
    
    @server.tool()
    def get_status(task_id: str, ctx: Context) -> str:
        """
        Query the status and progress of a task.
        
        Returns detailed information including:
        - Current status (running, completed, failed, cancelled)
        - Current step number and max steps
        - Plan history from all executed steps
        - Latest screenshot (base64 encoded PNG)
        - Error message if failed
        
        Args:
            task_id: The task identifier returned by run_task
            ctx: MCP context (automatically provided)
            
        Returns:
            JSON string with detailed task status
        """
        try:
            task = task_manager.get_task(task_id)
            
            if not task:
                return json.dumps({
                    "error": "Task not found",
                    "task_id": task_id
                })
            
            # Extract plan history
            plan_history = []
            for step in task.steps:
                if step.plan:
                    plan_history.append(f"Step {step.step_number + 1}: {step.plan}")
            
            # Build response
            response = TaskStatusResponse(
                task_id=task.task_id,
                status=task.status.value,
                current_step=task.current_step,
                max_steps=task.max_steps,
                plan_history=plan_history,
                latest_screenshot=task.latest_screenshot,
                error=task.error
            )
            
            return response.model_dump_json()
            
        except Exception as e:
            logger.error(f"Failed to get status: {e}")
            return json.dumps({
                "error": str(e),
                "task_id": task_id
            })
    
    @server.tool()
    def cancel_task(task_id: str, ctx: Context) -> str:
        """
        Cancel a running task.
        
        This will:
        1. Mark the task as cancelled
        2. Stop execution (note: current step may complete)
        
        Args:
            task_id: The task identifier to cancel
            ctx: MCP context (automatically provided)
            
        Returns:
            JSON string with cancellation status
        """
        try:
            task = task_manager.get_task(task_id)
            
            if not task:
                return json.dumps({
                    "error": "Task not found",
                    "task_id": task_id
                })
            
            if task.status != TaskStatus.RUNNING:
                return json.dumps({
                    "error": f"Task is not running (status: {task.status.value})",
                    "task_id": task_id,
                    "status": task.status.value
                })
            
            # Mark as cancelled
            task_manager.mark_complete(task_id, "cancelled")
            
            logger.info(f"Task {task_id} cancelled")
            
            return json.dumps({
                "task_id": task_id,
                "status": "cancelled",
                "message": "Task cancelled successfully"
            })
            
        except Exception as e:
            logger.error(f"Failed to cancel task: {e}")
            return json.dumps({
                "error": str(e),
                "task_id": task_id
            })
    
    # ========== RESOURCES ==========
    
    @server.resource("agent-s://tasks")
    def list_tasks(ctx: Context) -> str:
        """
        List all tasks for the current session.
        
        Returns a summary of all tasks including:
        - Task ID
        - Instruction
        - Status
        - Step progress
        - Creation/completion times
        """
        try:
            tasks = task_manager.list_tasks()
            
            # Build summary
            summary = []
            for task in tasks:
                summary.append({
                    "task_id": task.task_id,
                    "instruction": task.instruction,
                    "status": task.status.value,
                    "progress": f"{task.current_step}/{task.max_steps}",
                    "created_at": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(task.created_at)),
                    "completed_at": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(task.completed_at)) if task.completed_at else None,
                    "error": task.error
                })
            
            return json.dumps({
                "tasks": summary,
                "total": len(summary)
            }, indent=2)
            
        except Exception as e:
            logger.error(f"Failed to list tasks: {e}")
            return json.dumps({
                "error": str(e),
                "tasks": []
            })
    
    @server.resource("agent-s://screenshot/{task_id}")
    def get_screenshot(task_id: str, ctx: Context) -> str:
        """
        Get the latest screenshot for a task.
        
        Returns the most recent screenshot captured during task execution.
        The screenshot is base64 encoded PNG format.
        
        Args:
            task_id: Task identifier
        """
        try:
            task = task_manager.get_task(task_id)
            
            if not task:
                return json.dumps({
                    "error": "Task not found",
                    "task_id": task_id
                })
            
            if not task.latest_screenshot:
                return json.dumps({
                    "error": "No screenshot available",
                    "task_id": task_id,
                    "message": "Task may not have started yet or no screenshots captured"
                })
            
            return json.dumps({
                "task_id": task_id,
                "screenshot": task.latest_screenshot,
                "format": "base64_png",
                "status": task.status.value,
                "step": task.current_step
            })
            
        except Exception as e:
            logger.error(f"Failed to get screenshot: {e}")
            return json.dumps({
                "error": str(e),
                "task_id": task_id
            })
    
    # ========== PROMPTS ==========
    
    @server.prompt()
    def automate_task(task_description: str) -> list:
        """
        Generate a prompt for GUI task automation.
        
        This prompt helps structure task requests for Agent-S.
        
        Args:
            task_description: High-level description of the task
            
        Returns:
            Prompt messages for the LLM
        """
        return [
            {
                "role": "user",
                "content": f"""I need to automate this GUI task: {task_description}

Please use the run_task tool to execute this task with Agent-S.

Agent-S will:
1. Analyze the screen and task requirements
2. Generate and execute GUI actions automatically (clicks, typing, etc.)
3. Report progress in real-time
4. Complete the task or reach max steps

After starting the task, you can:
- Use get_status to check progress and see the latest screenshot
- Use cancel_task to stop execution if needed

What task would you like to execute?"""
            }
        ]
    
    return server
