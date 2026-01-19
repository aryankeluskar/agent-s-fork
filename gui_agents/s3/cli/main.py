#!/usr/bin/env python3
"""
Agent-S Unified CLI

Main entry point for all Agent-S commands:
    agent_s [run]       - Run the GUI agent (default)
    agent_s record      - Record workflows
    agent_s voice       - Voice assistant
    agent_s skills      - Manage skills

Usage:
    agent_s --provider openai --model gpt-4o ...
    agent_s run --provider anthropic --model claude-3-5-sonnet ...
    agent_s record start --name "open canvas"
    agent_s voice start
    agent_s skills list
"""

import argparse
import sys


def create_run_parser(subparsers):
    """Create the 'run' subcommand parser with all agent arguments."""
    from .run import add_run_arguments
    
    run_parser = subparsers.add_parser(
        "run",
        help="Run the Agent-S GUI agent",
        description="Execute Agent-S to automate GUI tasks",
    )
    add_run_arguments(run_parser)
    return run_parser


def create_record_parser(subparsers):
    """Create the 'record' subcommand parser."""
    from .record import add_record_arguments
    
    record_parser = subparsers.add_parser(
        "record",
        help="Record workflows for skill learning",
        description="Record mouse/keyboard events and screen for workflow analysis",
    )
    add_record_arguments(record_parser)
    return record_parser


def create_voice_parser(subparsers):
    """Create the 'voice' subcommand parser."""
    from .voice import add_voice_arguments
    
    voice_parser = subparsers.add_parser(
        "voice",
        help="Voice-activated assistant",
        description="Start voice assistant with wake word detection",
    )
    add_voice_arguments(voice_parser)
    return voice_parser


def create_skills_parser(subparsers):
    """Create the 'skills' subcommand parser."""
    from .skills import add_skills_arguments
    
    skills_parser = subparsers.add_parser(
        "skills",
        help="Manage learned skills",
        description="Search, list, and manage skills learned from recordings",
    )
    add_skills_arguments(skills_parser)
    return skills_parser


def main():
    """Main entry point for Agent-S CLI."""
    # Known subcommands
    subcommands = {"run", "record", "voice", "skills"}
    
    # Check if first argument is a subcommand or if we need to default to 'run'
    # This maintains backward compatibility: agent_s --provider openai ... 
    # should work the same as: agent_s run --provider openai ...
    if len(sys.argv) > 1:
        first_arg = sys.argv[1]
        # If first arg is not a subcommand and not -h/--help, insert 'run'
        if first_arg not in subcommands and first_arg not in ["-h", "--help"]:
            sys.argv.insert(1, "run")
    
    # Create top-level parser
    parser = argparse.ArgumentParser(
        prog="agent_s",
        description="Agent-S: GUI Automation Agent with Skill Learning",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  agent_s --provider openai --model gpt-4o --ground_provider vllm ...
  agent_s run --provider anthropic --model claude-3-5-sonnet ...
  agent_s record start --name "open canvas"
  agent_s voice start
  agent_s skills search "resize image"
        """,
    )
    
    # Create subparsers
    subparsers = parser.add_subparsers(
        dest="command",
        title="commands",
        description="Available commands (default: run)",
    )
    
    # Add subcommands
    create_run_parser(subparsers)
    create_record_parser(subparsers)
    create_voice_parser(subparsers)
    create_skills_parser(subparsers)
    
    # Parse arguments
    args = parser.parse_args()
    
    # If no command provided (just 'agent_s'), show help
    if args.command is None:
        parser.print_help()
        return 0
    
    # Dispatch to appropriate command handler
    if args.command == "run":
        from .run import cmd_run
        return cmd_run(args)
    
    elif args.command == "record":
        from .record import cmd_record
        return cmd_record(args)
    
    elif args.command == "voice":
        from .voice import cmd_voice
        return cmd_voice(args)
    
    elif args.command == "skills":
        from .skills import cmd_skills
        return cmd_skills(args)
    
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
