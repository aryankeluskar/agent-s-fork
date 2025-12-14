"""
Profiling infrastructure for Agent-S execution timing.

This module provides hierarchical profiling capabilities to track execution timing
at multiple granularity levels: steps, phases, functions, and API calls.
"""

import time
import logging
from contextlib import contextmanager
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from collections import defaultdict

logger = logging.getLogger("desktopenv.agent")


@dataclass
class TimingEntry:
    """Represents a single timing measurement."""
    name: str
    start_time: float
    end_time: Optional[float] = None
    duration: Optional[float] = None
    level: int = 0  # Hierarchy depth
    parent: Optional[str] = None
    children: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def finish(self):
        """Mark timing entry as complete and calculate duration."""
        self.end_time = time.perf_counter()
        self.duration = self.end_time - self.start_time


class ExecutionProfiler:
    """
    Global profiler singleton for tracking hierarchical execution timing.

    Usage:
        from gui_agents.s3.utils.profiler import profiler

        # Context manager (recommended)
        with profiler.profile("Operation_Name", metadata={"key": "value"}):
            # Code to profile
            pass

        # Manual timing
        key = profiler.start_timing("Operation_Name")
        # Code to profile
        profiler.end_timing(key)

        # Generate summary
        summary = profiler.generate_summary()
        print(summary)
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self.reset()

    def reset(self):
        """Reset profiler state for new task."""
        self.timings: Dict[str, TimingEntry] = {}
        self.timing_stack: List[str] = []  # Track current hierarchy
        self.current_level = 0
        self.enabled = True
        self.counter = 0  # For generating unique keys

    def start_timing(self, name: str, metadata: Optional[Dict] = None) -> str:
        """
        Start timing for a named block.

        Args:
            name: Name of the operation being timed
            metadata: Optional metadata to attach to this timing

        Returns:
            Unique key for this timing entry
        """
        if not self.enabled:
            return name

        # Generate unique key for this timing entry
        key = f"{name}_{self.counter}"
        self.counter += 1

        parent = self.timing_stack[-1] if self.timing_stack else None

        entry = TimingEntry(
            name=name,
            start_time=time.perf_counter(),
            level=self.current_level,
            parent=parent,
            metadata=metadata or {}
        )

        self.timings[key] = entry

        # Update parent's children
        if parent and parent in self.timings:
            self.timings[parent].children.append(key)

        # Push to stack
        self.timing_stack.append(key)
        self.current_level += 1

        return key

    def end_timing(self, key: str) -> float:
        """
        End timing for a named block and log the result.

        Args:
            key: Unique key returned by start_timing

        Returns:
            Duration in seconds
        """
        if not self.enabled or key not in self.timings:
            return 0.0

        entry = self.timings[key]
        entry.finish()

        # Pop from stack
        if self.timing_stack and self.timing_stack[-1] == key:
            self.timing_stack.pop()
            self.current_level -= 1

        # Log with hierarchy-aware formatting
        indent = "  " * entry.level
        duration_ms = entry.duration * 1000

        # Add metadata to log if present
        meta_str = ""
        if entry.metadata:
            # Format metadata as compact dict
            meta_items = ", ".join([f"'{k}': {repr(v)}" for k, v in entry.metadata.items()])
            meta_str = f" | {{{meta_items}}}"

        logger.info(f"⏱️  {indent}{entry.name}: {duration_ms:.2f}ms{meta_str}")

        return entry.duration

    def add_metadata(self, key: str, metadata: Dict):
        """
        Add metadata to existing timing entry.

        Args:
            key: Unique key of the timing entry
            metadata: Metadata to add/update
        """
        if key in self.timings:
            self.timings[key].metadata.update(metadata)

    @contextmanager
    def profile(self, name: str, metadata: Optional[Dict] = None):
        """
        Context manager for timing a block of code.

        Args:
            name: Name of the operation being timed
            metadata: Optional metadata to attach to this timing

        Yields:
            Unique key for this timing entry (can be used to add metadata)
        """
        key = self.start_timing(name, metadata)
        try:
            yield key
        finally:
            self.end_timing(key)

    def generate_summary(self) -> str:
        """
        Generate a summary table of all timings.

        Returns:
            Formatted summary string
        """
        if not self.timings:
            return "No timing data collected"

        # Aggregate timings by name (ignore unique suffixes)
        aggregated = defaultdict(lambda: {
            "count": 0,
            "total": 0.0,
            "min": float('inf'),
            "max": 0.0,
            "durations": []
        })

        for key, entry in self.timings.items():
            if entry.duration is None:
                continue

            name = entry.name
            duration = entry.duration

            aggregated[name]["count"] += 1
            aggregated[name]["total"] += duration
            aggregated[name]["min"] = min(aggregated[name]["min"], duration)
            aggregated[name]["max"] = max(aggregated[name]["max"], duration)
            aggregated[name]["durations"].append(duration)

        # Calculate averages and sort by total time
        summary_data = []
        for name, stats in aggregated.items():
            avg = stats["total"] / stats["count"]
            summary_data.append({
                "name": name,
                "count": stats["count"],
                "total": stats["total"],
                "avg": avg,
                "min": stats["min"],
                "max": stats["max"]
            })

        summary_data.sort(key=lambda x: x["total"], reverse=True)

        # Format as table
        lines = []
        lines.append("\n" + "="*100)
        lines.append("EXECUTION PROFILING SUMMARY")
        lines.append("="*100)
        lines.append(f"{'Operation':<40} {'Count':>8} {'Total (ms)':>12} {'Avg (ms)':>12} {'Min (ms)':>12} {'Max (ms)':>12}")
        lines.append("-"*100)

        for data in summary_data:
            lines.append(
                f"{data['name']:<40} "
                f"{data['count']:>8} "
                f"{data['total']*1000:>12.2f} "
                f"{data['avg']*1000:>12.2f} "
                f"{data['min']*1000:>12.2f} "
                f"{data['max']*1000:>12.2f}"
            )

        lines.append("="*100)

        # Calculate total execution time (top-level entries only)
        total_time = sum(
            entry.duration for entry in self.timings.values()
            if entry.duration is not None and entry.level == 0
        )
        lines.append(f"Total Execution Time: {total_time*1000:.2f}ms ({total_time:.2f}s)")
        lines.append("="*100)

        return "\n".join(lines)


# Global profiler instance
profiler = ExecutionProfiler()
