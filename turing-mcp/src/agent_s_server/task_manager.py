"""
Thread-safe task state management for Agent-S MCP server.
"""

import base64
import time
import threading
from typing import Optional, Dict, List
from multiprocessing import Manager

from .models import TaskState, TaskStatus, StepInfo


class TaskManager:
    """
    Thread-safe manager for task state using multiprocessing.Manager.
    Provides CRUD operations and automatic cleanup of old tasks.
    """
    
    def __init__(self, cleanup_age_hours: int = 24):
        """
        Initialize TaskManager.
        
        Args:
            cleanup_age_hours: Tasks older than this will be cleaned up
        """
        # Use multiprocessing Manager for inter-process shared state
        self._manager = Manager()
        self._tasks = self._manager.dict()
        
        # Thread lock for atomic operations within server process
        self._lock = threading.Lock()
        
        self.cleanup_age_hours = cleanup_age_hours
    
    def create_task(
        self,
        task_id: str,
        instruction: str,
        max_steps: int = 15
    ) -> TaskState:
        """
        Create a new task.
        
        Args:
            task_id: Unique task identifier
            instruction: Task instruction
            max_steps: Maximum number of steps
            
        Returns:
            TaskState object
        """
        with self._lock:
            now = time.time()
            task = TaskState(
                task_id=task_id,
                instruction=instruction,
                status=TaskStatus.PENDING,
                current_step=0,
                max_steps=max_steps,
                steps=[],
                latest_screenshot=None,
                error=None,
                created_at=now,
                updated_at=now,
                completed_at=None
            )
            
            # Convert to dict for storage in Manager.dict
            self._tasks[task_id] = task.model_dump()
            return task
    
    def get_task(self, task_id: str) -> Optional[TaskState]:
        """
        Get task by ID.
        
        Args:
            task_id: Task identifier
            
        Returns:
            TaskState object or None if not found
        """
        with self._lock:
            task_dict = self._tasks.get(task_id)
            if task_dict:
                return TaskState(**task_dict)
            return None
    
    def update_task_status(
        self,
        task_id: str,
        status: TaskStatus,
        error: Optional[str] = None
    ) -> bool:
        """
        Update task status.
        
        Args:
            task_id: Task identifier
            status: New status
            error: Optional error message
            
        Returns:
            True if successful, False if task not found
        """
        with self._lock:
            if task_id not in self._tasks:
                return False
            
            task_dict = self._tasks[task_id]
            task_dict['status'] = status.value
            task_dict['updated_at'] = time.time()
            
            if error:
                task_dict['error'] = error
            
            if status in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED]:
                task_dict['completed_at'] = time.time()
            
            self._tasks[task_id] = task_dict
            return True
    
    def update_step(
        self,
        task_id: str,
        step_number: int,
        plan: Optional[str] = None,
        reflection: Optional[str] = None,
        code: Optional[str] = None,
        error: Optional[str] = None,
        screenshot: Optional[bytes] = None
    ) -> bool:
        """
        Update task with new step information.
        
        Args:
            task_id: Task identifier
            step_number: Step number (0-indexed)
            plan: Plan/action description
            reflection: Reflection text
            code: Code to execute
            error: Error message if any
            screenshot: Screenshot bytes (will be base64 encoded)
            
        Returns:
            True if successful, False if task not found
        """
        with self._lock:
            if task_id not in self._tasks:
                return False
            
            task_dict = self._tasks[task_id]
            
            # Create step info
            step_info = StepInfo(
                step_number=step_number,
                plan=plan,
                reflection=reflection,
                code=code,
                error=error,
                timestamp=time.time()
            )
            
            # Update task
            task_dict['steps'].append(step_info.model_dump())
            task_dict['current_step'] = step_number
            task_dict['updated_at'] = time.time()
            
            # Update screenshot if provided (store only latest to avoid memory bloat)
            if screenshot:
                task_dict['latest_screenshot'] = base64.b64encode(screenshot).decode('utf-8')
            
            # Update status to running if not already
            if task_dict['status'] == TaskStatus.PENDING.value:
                task_dict['status'] = TaskStatus.RUNNING.value
            
            self._tasks[task_id] = task_dict
            return True
    
    def mark_complete(self, task_id: str, status: str, error: Optional[str] = None) -> bool:
        """
        Mark task as complete, failed, or cancelled.
        
        Args:
            task_id: Task identifier
            status: Final status ("success", "failed", "cancelled")
            error: Optional error message
            
        Returns:
            True if successful, False if task not found
        """
        status_map = {
            "success": TaskStatus.COMPLETED,
            "completed": TaskStatus.COMPLETED,
            "failed": TaskStatus.FAILED,
            "cancelled": TaskStatus.CANCELLED
        }
        
        final_status = status_map.get(status.lower(), TaskStatus.FAILED)
        return self.update_task_status(task_id, final_status, error)
    
    def list_tasks(self) -> List[TaskState]:
        """
        List all tasks.
        
        Returns:
            List of TaskState objects
        """
        with self._lock:
            return [TaskState(**task_dict) for task_dict in self._tasks.values()]
    
    def get_running_tasks(self) -> List[str]:
        """
        Get list of running task IDs.
        
        Returns:
            List of task IDs with status RUNNING
        """
        with self._lock:
            return [
                task_id 
                for task_id, task_dict in self._tasks.items() 
                if task_dict['status'] == TaskStatus.RUNNING.value
            ]
    
    def cleanup_old_tasks(self) -> int:
        """
        Remove tasks older than cleanup_age_hours.
        
        Returns:
            Number of tasks cleaned up
        """
        with self._lock:
            now = time.time()
            cutoff = now - (self.cleanup_age_hours * 3600)
            
            to_remove = [
                task_id
                for task_id, task_dict in self._tasks.items()
                if task_dict['created_at'] < cutoff
            ]
            
            for task_id in to_remove:
                del self._tasks[task_id]
            
            return len(to_remove)
    
    def delete_task(self, task_id: str) -> bool:
        """
        Delete a specific task.
        
        Args:
            task_id: Task identifier
            
        Returns:
            True if deleted, False if not found
        """
        with self._lock:
            if task_id in self._tasks:
                del self._tasks[task_id]
                return True
            return False
