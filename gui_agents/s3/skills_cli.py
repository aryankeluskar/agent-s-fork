#!/usr/bin/env python3
"""
Skills CLI for Agent-S

Command-line interface for managing recordings and skills:
- Record workflows (start/stop recording)
- Process recordings into skills
- Search and list skills
- Compose plans from skills

Usage:
    python skills_cli.py record --name "open canvas"
    python skills_cli.py process /path/to/recording/
    python skills_cli.py search "resize image"
    python skills_cli.py list
    python skills_cli.py compose "download and resize image"
"""

import argparse
import json
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()


def cmd_record(args):
    """Start/stop recording a workflow."""
    from gui_agents.s3.recording import Recorder, get_recordings_dir, get_latest_recording
    
    if args.action == "start":
        print(f"Starting recording: {args.name or 'unnamed'}")
        print("Press Ctrl+C to stop recording...\n")
        
        recorder = Recorder(
            recording_name=args.name,
            capture_screenshots=not args.no_screenshots,
            screenshot_interval=args.screenshot_interval,
        )
        
        recorder.start()
        
        try:
            while recorder.is_recording:
                time.sleep(0.5)
        except KeyboardInterrupt:
            print("\n\nStopping recording...")
        
        recording_path = recorder.stop()
        print(f"\nRecording saved to: {recording_path}")
        
        # Offer to process
        if args.process:
            print("\nProcessing recording...")
            from gui_agents.s3.recording import process_recording
            results = process_recording(recording_path)
            if results["success"]:
                print(f"Skill indexed with ID: {results['skill_id']}")
            else:
                print(f"Processing failed: {results['errors']}")
        
        return 0
    
    elif args.action == "list":
        recordings_dir = get_recordings_dir()
        print(f"Recordings directory: {recordings_dir}\n")
        
        recordings = sorted(
            [d for d in recordings_dir.iterdir() if d.is_dir()],
            key=lambda x: x.stat().st_mtime,
            reverse=True
        )
        
        if not recordings:
            print("No recordings found.")
            return 0
        
        print("Recent recordings:")
        for r in recordings[:20]:
            metadata_path = r / "metadata.json"
            if metadata_path.exists():
                metadata = json.loads(metadata_path.read_text())
                duration = metadata.get("duration_seconds", 0)
                print(f"  - {r.name} ({duration:.1f}s)")
            else:
                print(f"  - {r.name}")
        
        return 0
    
    elif args.action == "latest":
        latest = get_latest_recording()
        if latest:
            print(f"Latest recording: {latest}")
        else:
            print("No recordings found.")
        return 0
    
    return 0


def cmd_process(args):
    """Process a recording into a skill."""
    from gui_agents.s3.recording import process_recording, get_latest_recording
    
    # Determine recording path
    if args.recording:
        recording_path = Path(args.recording)
    else:
        recording_path = get_latest_recording()
        if not recording_path:
            print("Error: No recordings found. Specify a path or record first.")
            return 1
    
    if not recording_path.exists():
        print(f"Error: Recording not found: {recording_path}")
        return 1
    
    print(f"Processing: {recording_path}")
    
    def progress_callback(msg, pct):
        print(f"[{pct:3d}%] {msg}")
    
    def error_callback(stage, e):
        print(f"ERROR in {stage}: {e}")
    
    results = process_recording(
        recording_path,
        on_progress=progress_callback,
        on_error=error_callback,
    )
    
    print("\n" + "=" * 50)
    if results["success"]:
        print(f"SUCCESS: Skill indexed with ID: {results['skill_id']}")
        print(f"Log file: {results['log_file']}")
    else:
        print(f"FAILED: {results['errors']}")
    
    return 0 if results["success"] else 1


def cmd_search(args):
    """Search for skills."""
    from gui_agents.s3.skills import SkillStore, SkillRetriever
    
    store = SkillStore()
    
    if store.stats()["total_skills"] == 0:
        print("No skills indexed. Record and process some workflows first.")
        return 0
    
    retriever = SkillRetriever(store)
    
    results = retriever.retrieve_with_steps(
        query=args.query,
        n_skills=args.limit,
        n_steps_per_skill=3,
    )
    
    if not results:
        print(f"No skills found matching: {args.query}")
        return 0
    
    print(f"Found {len(results)} skills:\n")
    
    for i, result in enumerate(results, 1):
        skill = result.skill
        print(f"{i}. {skill.name}")
        print(f"   Score: {result.score:.2f} ({result.match_reason})")
        print(f"   Summary: {skill.summary[:100]}..." if len(skill.summary) > 100 else f"   Summary: {skill.summary}")
        print(f"   Steps: {len(skill.steps)}")
        print(f"   ID: {skill.id}")
        
        if result.matched_steps and args.verbose:
            print("   Matched steps:")
            for step, score in result.matched_steps[:3]:
                print(f"     - {step.title} (score: {score:.2f})")
        print()
    
    return 0


def cmd_list(args):
    """List all indexed skills."""
    from gui_agents.s3.skills import SkillStore
    
    store = SkillStore()
    stats = store.stats()
    
    print(f"Skill Store: {stats['store_path']}")
    print(f"Total skills: {stats['total_skills']}")
    print(f"Total steps: {stats['total_steps']}")
    print()
    
    skills = store.get_all_skills()
    
    if not skills:
        print("No skills indexed. Record and process some workflows first.")
        return 0
    
    print("Indexed skills:")
    for skill in skills:
        print(f"\n  {skill.name}")
        print(f"    ID: {skill.id}")
        print(f"    Steps: {len(skill.steps)}")
        print(f"    OS: {skill.metadata.operating_system or 'unknown'}")
        print(f"    Apps: {', '.join(skill.metadata.applications) or 'none'}")
        if args.verbose:
            print(f"    Summary: {skill.summary[:80]}...")
    
    return 0


def cmd_compose(args):
    """Compose a plan from skills."""
    from gui_agents.s3.skills import SkillStore, SkillRetriever, SkillComposer
    import platform
    
    store = SkillStore()
    
    if store.stats()["total_skills"] == 0:
        print("No skills indexed. Record and process some workflows first.")
        return 0
    
    retriever = SkillRetriever(store)
    composer = SkillComposer(retriever)
    
    print(f"Composing plan for: {args.goal}\n")
    
    plan = composer.compose_plan(
        goal=args.goal,
        os_info=platform.system(),
    )
    
    print(f"Confidence: {plan.confidence:.0%}")
    print(f"Skills used: {len(plan.skills_used)}")
    
    if plan.skills_used:
        print("\nSkills:")
        for skill in plan.skills_used:
            print(f"  - {skill.name}")
    
    print("\nExecution Plan:")
    for step in plan.steps:
        print(f"  {step['number']}. {step['description']}")
        if args.verbose and step.get('parameters'):
            print(f"      Parameters: {step['parameters']}")
    
    if plan.reasoning:
        print(f"\nReasoning: {plan.reasoning}")
    
    return 0


def cmd_delete(args):
    """Delete a skill."""
    from gui_agents.s3.skills import SkillStore
    
    store = SkillStore()
    
    if args.skill_id == "all":
        confirm = input("Delete ALL skills? Type 'yes' to confirm: ")
        if confirm.lower() == "yes":
            store.clear()
            print("All skills deleted.")
        else:
            print("Cancelled.")
        return 0
    
    skill = store.get_skill(args.skill_id)
    if not skill:
        print(f"Skill not found: {args.skill_id}")
        return 1
    
    confirm = input(f"Delete skill '{skill.name}'? (y/n): ")
    if confirm.lower() == "y":
        store.delete_skill(args.skill_id)
        print("Skill deleted.")
    else:
        print("Cancelled.")
    
    return 0


def cmd_context(args):
    """Manage user context."""
    from gui_agents.s3.skills import UserContextStore
    
    store = UserContextStore()
    
    if args.action == "list":
        contexts = store.get_all()
        
        if not contexts:
            print("No user context stored.")
            return 0
        
        print(f"User Context ({len(contexts)} items):\n")
        for ctx in contexts:
            print(f"  {ctx.key}: {ctx.value}")
            print(f"    Type: {ctx.context_type.value}, App: {ctx.application}")
            if ctx.description:
                print(f"    Description: {ctx.description}")
            print()
    
    elif args.action == "search":
        if not args.query:
            print("Error: --query required for search")
            return 1
        
        results = store.search(args.query)
        
        if not results:
            print(f"No context found matching: {args.query}")
            return 0
        
        print(f"Found {len(results)} matches:\n")
        for ctx in results:
            print(f"  {ctx.key}: {ctx.value} ({ctx.context_type.value})")
    
    elif args.action == "clear":
        confirm = input("Clear all user context? Type 'yes' to confirm: ")
        if confirm.lower() == "yes":
            store.clear()
            print("User context cleared.")
        else:
            print("Cancelled.")
    
    return 0


def main():
    parser = argparse.ArgumentParser(
        description="Agent-S Skills CLI - Manage recordings and learned workflows",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # Record command
    record_parser = subparsers.add_parser("record", help="Manage recordings")
    record_parser.add_argument("action", choices=["start", "list", "latest"], help="Action to perform")
    record_parser.add_argument("--name", "-n", help="Name for the recording")
    record_parser.add_argument("--no-screenshots", action="store_true", help="Disable screenshot capture")
    record_parser.add_argument("--screenshot-interval", type=float, default=1.0, help="Screenshot interval in seconds")
    record_parser.add_argument("--process", "-p", action="store_true", help="Process recording after stopping")
    record_parser.set_defaults(func=cmd_record)
    
    # Process command
    process_parser = subparsers.add_parser("process", help="Process a recording into a skill")
    process_parser.add_argument("recording", nargs="?", help="Path to recording (default: latest)")
    process_parser.set_defaults(func=cmd_process)
    
    # Search command
    search_parser = subparsers.add_parser("search", help="Search for skills")
    search_parser.add_argument("query", help="Search query")
    search_parser.add_argument("--limit", "-l", type=int, default=5, help="Max results")
    search_parser.add_argument("--verbose", "-v", action="store_true", help="Show matched steps")
    search_parser.set_defaults(func=cmd_search)
    
    # List command
    list_parser = subparsers.add_parser("list", help="List all skills")
    list_parser.add_argument("--verbose", "-v", action="store_true", help="Show summaries")
    list_parser.set_defaults(func=cmd_list)
    
    # Compose command
    compose_parser = subparsers.add_parser("compose", help="Compose a plan from skills")
    compose_parser.add_argument("goal", help="Goal to accomplish")
    compose_parser.add_argument("--verbose", "-v", action="store_true", help="Show parameters")
    compose_parser.set_defaults(func=cmd_compose)
    
    # Delete command
    delete_parser = subparsers.add_parser("delete", help="Delete a skill")
    delete_parser.add_argument("skill_id", help="Skill ID to delete (or 'all')")
    delete_parser.set_defaults(func=cmd_delete)
    
    # Context command
    context_parser = subparsers.add_parser("context", help="Manage user context")
    context_parser.add_argument("action", choices=["list", "search", "clear"], help="Action")
    context_parser.add_argument("--query", "-q", help="Search query")
    context_parser.set_defaults(func=cmd_context)
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 1
    
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
