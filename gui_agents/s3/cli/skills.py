"""
Agent-S Skills Command

Manage learned skills from recordings:
- Search for skills by query
- List all indexed skills
- Compose plans from skills
- Delete skills
- Manage user context
"""

import json
import platform
import sys


def cmd_skills_search(args):
    """Search for skills."""
    from gui_agents.s3.skills import SkillStore, SkillRetriever
    
    store = SkillStore()
    
    if store.stats()["total_skills"] == 0:
        print("No skills indexed. Record and process some workflows first.")
        print("\n💡 Tip: Run 'agent_s record start --name \"my task\"'")
        return 0
    
    retriever = SkillRetriever(store)
    
    print(f"\n🔍 Searching for: {args.query}\n")
    
    results = retriever.retrieve_with_steps(
        query=args.query,
        n_skills=args.limit,
        n_steps_per_skill=3,
    )
    
    if not results:
        print(f"No skills found matching: {args.query}")
        return 0
    
    print(f"Found {len(results)} skill(s):\n")
    
    for i, result in enumerate(results, 1):
        skill = result.skill
        summary = skill.summary[:100] + "..." if len(skill.summary) > 100 else skill.summary
        
        print(f"{i}. {skill.name}")
        print(f"   Score: {result.score:.2f} ({result.match_reason})")
        print(f"   Summary: {summary}")
        print(f"   Steps: {len(skill.steps)}")
        print(f"   ID: {skill.id}")
        
        if result.matched_steps and args.verbose:
            print("   Matched steps:")
            for step, score in result.matched_steps[:3]:
                print(f"     - {step.title} (score: {score:.2f})")
        print()
    
    return 0


def cmd_skills_list(args):
    """List all indexed skills."""
    from gui_agents.s3.skills import SkillStore
    
    store = SkillStore()
    stats = store.stats()
    
    print(f"\n📦 Skill Store")
    print(f"   Path: {stats['store_path']}")
    print(f"   Total skills: {stats['total_skills']}")
    print(f"   Total steps: {stats['total_steps']}")
    
    skills = store.get_all_skills()
    
    if not skills:
        print("\nNo skills indexed.")
        print("\n💡 Tip: Run 'agent_s record start --name \"my task\"' to learn a new skill")
        return 0
    
    print("\n" + "-" * 60)
    print("Indexed Skills:")
    print("-" * 60)
    
    for skill in skills:
        print(f"\n  📋 {skill.name}")
        print(f"     ID: {skill.id}")
        print(f"     Steps: {len(skill.steps)}")
        print(f"     OS: {skill.metadata.operating_system or 'unknown'}")
        print(f"     Apps: {', '.join(skill.metadata.applications) or 'none'}")
        if args.verbose:
            summary = skill.summary[:80] + "..." if len(skill.summary) > 80 else skill.summary
            print(f"     Summary: {summary}")
    
    return 0


def cmd_skills_compose(args):
    """Compose a plan from skills."""
    from gui_agents.s3.skills import SkillStore, SkillRetriever, SkillComposer
    
    store = SkillStore()
    
    if store.stats()["total_skills"] == 0:
        print("No skills indexed. Record and process some workflows first.")
        return 0
    
    retriever = SkillRetriever(store)
    composer = SkillComposer(retriever)
    
    print(f"\n🎯 Composing plan for: {args.goal}\n")
    
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
    
    print("\n📝 Execution Plan:")
    print("-" * 40)
    for step in plan.steps:
        print(f"  {step['number']}. {step['description']}")
        if args.verbose and step.get('parameters'):
            print(f"      Parameters: {step['parameters']}")
    
    if plan.reasoning:
        print(f"\n💭 Reasoning: {plan.reasoning}")
    
    return 0


def cmd_skills_delete(args):
    """Delete a skill."""
    from gui_agents.s3.skills import SkillStore
    
    store = SkillStore()
    
    if args.skill_id == "all":
        confirm = input("⚠️  Delete ALL skills? Type 'yes' to confirm: ")
        if confirm.lower() == "yes":
            store.clear()
            print("✅ All skills deleted.")
        else:
            print("Cancelled.")
        return 0
    
    skill = store.get_skill(args.skill_id)
    if not skill:
        print(f"❌ Skill not found: {args.skill_id}")
        return 1
    
    confirm = input(f"Delete skill '{skill.name}'? (y/n): ")
    if confirm.lower() == "y":
        store.delete_skill(args.skill_id)
        print("✅ Skill deleted.")
    else:
        print("Cancelled.")
    
    return 0


def cmd_skills_context(args):
    """Manage user context."""
    from gui_agents.s3.skills import UserContextStore
    
    store = UserContextStore()
    
    if args.context_action == "list":
        contexts = store.get_all()
        
        if not contexts:
            print("No user context stored.")
            return 0
        
        print(f"\n👤 User Context ({len(contexts)} items):\n")
        for ctx in contexts:
            print(f"  {ctx.key}: {ctx.value}")
            print(f"    Type: {ctx.context_type.value}, App: {ctx.application}")
            if ctx.description:
                print(f"    Description: {ctx.description}")
            print()
    
    elif args.context_action == "search":
        if not args.query:
            print("❌ --query required for search")
            return 1
        
        results = store.search(args.query)
        
        if not results:
            print(f"No context found matching: {args.query}")
            return 0
        
        print(f"\n🔍 Found {len(results)} match(es):\n")
        for ctx in results:
            print(f"  {ctx.key}: {ctx.value} ({ctx.context_type.value})")
    
    elif args.context_action == "clear":
        confirm = input("⚠️  Clear all user context? Type 'yes' to confirm: ")
        if confirm.lower() == "yes":
            store.clear()
            print("✅ User context cleared.")
        else:
            print("Cancelled.")
    
    return 0


def add_skills_arguments(parser):
    """Add arguments for the skills command."""
    subparsers = parser.add_subparsers(dest="skills_action", help="Skills actions")
    
    # Search subcommand
    search_parser = subparsers.add_parser("search", help="Search for skills")
    search_parser.add_argument("query", help="Search query")
    search_parser.add_argument(
        "--limit", "-l",
        type=int,
        default=5,
        help="Maximum results (default: 5)",
    )
    search_parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show matched steps",
    )
    
    # List subcommand
    list_parser = subparsers.add_parser("list", help="List all skills")
    list_parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show summaries",
    )
    
    # Compose subcommand
    compose_parser = subparsers.add_parser("compose", help="Compose a plan from skills")
    compose_parser.add_argument("goal", help="Goal to accomplish")
    compose_parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show parameters",
    )
    
    # Delete subcommand
    delete_parser = subparsers.add_parser("delete", help="Delete a skill")
    delete_parser.add_argument("skill_id", help="Skill ID to delete (or 'all')")
    
    # Context subcommand
    context_parser = subparsers.add_parser("context", help="Manage user context")
    context_subparsers = context_parser.add_subparsers(dest="context_action")
    
    context_subparsers.add_parser("list", help="List all context")
    
    context_search = context_subparsers.add_parser("search", help="Search context")
    context_search.add_argument("--query", "-q", required=True, help="Search query")
    
    context_subparsers.add_parser("clear", help="Clear all context")


def cmd_skills(args):
    """Handle skills command dispatch."""
    if not hasattr(args, "skills_action") or args.skills_action is None:
        print("Usage: agent_s skills {search|list|compose|delete|context}")
        print("\nCommands:")
        print("  search   Search for skills by query")
        print("  list     List all indexed skills")
        print("  compose  Generate a plan from skills")
        print("  delete   Delete a skill")
        print("  context  Manage user context")
        return 1
    
    if args.skills_action == "search":
        return cmd_skills_search(args)
    elif args.skills_action == "list":
        return cmd_skills_list(args)
    elif args.skills_action == "compose":
        return cmd_skills_compose(args)
    elif args.skills_action == "delete":
        return cmd_skills_delete(args)
    elif args.skills_action == "context":
        return cmd_skills_context(args)
    else:
        print(f"Unknown skills action: {args.skills_action}")
        return 1
