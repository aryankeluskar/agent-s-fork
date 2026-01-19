"""
Agent-S Run Command

Executes the Agent-S GUI automation agent.
Extracted from the original cli_app.py for the unified CLI.
"""

import datetime
import io
import logging
import os
import platform
import signal
import sys
import time

import pyautogui
from PIL import Image

# Global flag to track pause state for debugging
paused = False


def get_char():
    """Get a single character from stdin without pressing Enter."""
    try:
        if platform.system() in ["Darwin", "Linux"]:
            import termios
            import tty

            fd = sys.stdin.fileno()
            old_settings = termios.tcgetattr(fd)
            try:
                tty.setraw(sys.stdin.fileno())
                ch = sys.stdin.read(1)
            finally:
                termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
            return ch
        else:
            import msvcrt
            return msvcrt.getch().decode("utf-8", errors="ignore")
    except Exception:
        return input()


def signal_handler(signum, frame):
    """Handle Ctrl+C signal for debugging during agent execution."""
    global paused

    if not paused:
        print("\n\n🔸 Agent-S Workflow Paused 🔸")
        print("=" * 50)
        print("Options:")
        print("  • Press Ctrl+C again to quit")
        print("  • Press Esc to resume workflow")
        print("=" * 50)

        paused = True

        while paused:
            try:
                print("\n[PAUSED] Waiting for input... ", end="", flush=True)
                char = get_char()

                if ord(char) == 3:  # Ctrl+C
                    print("\n\n🛑 Exiting Agent-S...")
                    sys.exit(0)
                elif ord(char) == 27:  # Esc
                    print("\n\n▶️  Resuming Agent-S workflow...")
                    paused = False
                    break
                else:
                    print(f"\n   Unknown command: '{char}' (ord: {ord(char)})")

            except KeyboardInterrupt:
                print("\n\n🛑 Exiting Agent-S...")
                sys.exit(0)
    else:
        print("\n\n🛑 Exiting Agent-S...")
        sys.exit(0)


def setup_logging():
    """Configure logging for the agent."""
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)

    datetime_str = datetime.datetime.now().strftime("%Y%m%d@%H%M%S")

    log_dir = "logs"
    os.makedirs(log_dir, exist_ok=True)

    file_handler = logging.FileHandler(
        os.path.join("logs", f"normal-{datetime_str}.log"), encoding="utf-8"
    )
    debug_handler = logging.FileHandler(
        os.path.join("logs", f"debug-{datetime_str}.log"), encoding="utf-8"
    )
    stdout_handler = logging.StreamHandler(sys.stdout)
    sdebug_handler = logging.FileHandler(
        os.path.join("logs", f"sdebug-{datetime_str}.log"), encoding="utf-8"
    )

    file_handler.setLevel(logging.INFO)
    debug_handler.setLevel(logging.DEBUG)
    stdout_handler.setLevel(logging.INFO)
    sdebug_handler.setLevel(logging.DEBUG)

    formatter = logging.Formatter(
        fmt="\x1b[1;33m[%(asctime)s \x1b[31m%(levelname)s \x1b[32m%(module)s/%(lineno)d-%(processName)s\x1b[1;33m] \x1b[0m%(message)s"
    )
    file_handler.setFormatter(formatter)
    debug_handler.setFormatter(formatter)
    stdout_handler.setFormatter(formatter)
    sdebug_handler.setFormatter(formatter)

    stdout_handler.addFilter(logging.Filter("desktopenv"))
    sdebug_handler.addFilter(logging.Filter("desktopenv"))

    logger.addHandler(file_handler)
    logger.addHandler(debug_handler)
    logger.addHandler(stdout_handler)
    logger.addHandler(sdebug_handler)

    return logger


def scale_screen_dimensions(width: int, height: int, max_dim_size: int):
    """Scale screen dimensions to fit within max size."""
    scale_factor = min(max_dim_size / width, max_dim_size / height, 1)
    safe_width = int(width * scale_factor)
    safe_height = int(height * scale_factor)
    return safe_width, safe_height


def run_agent(agent, instruction: str, scaled_width: int, scaled_height: int, use_robotgo: bool = False):
    """Run the agent execution loop."""
    from gui_agents.s3.utils.profiler import profiler
    from gui_agents.s3.utils.common_utils import compress_image

    global paused
    obs = {}
    traj = "Task:\n" + instruction

    # Reset profiler for new task
    profiler.reset()
    logger = logging.getLogger()

    for step in range(15):
        with profiler.profile(f"Step_{step+1}"):
            # Check if we're in paused state and wait
            while paused:
                time.sleep(0.1)

            # Get screen shot using mss (faster than pyautogui)
            with profiler.profile("Screenshot_Capture"):
                import mss
                with mss.mss() as sct:
                    monitor = sct.monitors[1]
                    sct_img = sct.grab(monitor)
                    screenshot = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")

                screenshot = screenshot.resize((scaled_width, scaled_height), Image.BICUBIC)
                screenshot_bytes = compress_image(image=screenshot)
                obs["screenshot"] = screenshot_bytes

            while paused:
                time.sleep(0.1)

            print(f"\n🔄 Step {step + 1}/15: Getting next action from agent...")

            with profiler.profile("Agent_Prediction"):
                info, code = agent.predict(instruction=instruction, observation=obs)

            if "done" in code[0].lower() or "fail" in code[0].lower():
                logger.info(f"Agent completed task on step {step + 1}. Code: {code[0]}")

                if platform.system() == "Darwin":
                    os.system(
                        'osascript -e \'display dialog "Task Completed" with title "Agent-S" buttons "OK" default button "OK"\''
                    )
                elif platform.system() == "Linux":
                    os.system(
                        'zenity --info --title="Agent-S" --text="Task Completed" --width=200 --height=100'
                    )
                break

            if "next" in code[0].lower():
                continue

            if "wait" in code[0].lower():
                print("⏳ Agent requested wait...")
                time.sleep(5)
                continue

            else:
                time.sleep(0.1)
                print("EXECUTING CODE:", code[0])

                while paused:
                    time.sleep(0.1)

                with profiler.profile("Code_Execution"):
                    if use_robotgo:
                        from gui_agents.s3.utils.robotgo_executor import execute_robotgo_code
                        success = execute_robotgo_code(code[0])
                        if not success:
                            logger.error("Failed to execute robotgo code")
                    else:
                        exec(code[0])
                time.sleep(0.2)

                if "reflection" in info and "executor_plan" in info:
                    traj += (
                        "\n\nReflection:\n"
                        + str(info["reflection"])
                        + "\n\n----------------------\n\nPlan:\n"
                        + info["executor_plan"]
                    )

    # Display grounding cache statistics
    if hasattr(agent, "executor") and hasattr(agent.executor, "grounding_agent"):
        grounding_agent = agent.executor.grounding_agent
        if hasattr(grounding_agent, "_cache_hits"):
            total_calls = grounding_agent._cache_hits + grounding_agent._cache_misses
            hit_rate = (grounding_agent._cache_hits / total_calls * 100) if total_calls > 0 else 0
            time_saved = grounding_agent._cache_hits * 1.3
            print("\n" + "=" * 100)
            print("GROUNDING CACHE STATISTICS")
            print("=" * 100)
            print(f"Cache Hits:       {grounding_agent._cache_hits}")
            print(f"Cache Misses:     {grounding_agent._cache_misses}")
            print(f"Total Calls:      {total_calls}")
            print(f"Hit Rate:         {hit_rate:.1f}%")
            print(f"Est. Time Saved:  ~{time_saved:.1f}s")
            print("=" * 100 + "\n")

    summary = profiler.generate_summary()
    logger.info(summary)
    print(summary)


def add_run_arguments(parser):
    """Add all arguments for the run command."""
    # Main model configuration
    parser.add_argument(
        "--provider",
        type=str,
        default="openai",
        help="Provider for main model. Options: openai, anthropic, gemini, open_router, cerebras, azure, vllm, huggingface, parasail",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="gpt-4o",
        help="Main model name. Examples: gpt-4o, claude-3-5-sonnet-20241022, gemini-2.0-flash-exp",
    )
    parser.add_argument(
        "--model_url",
        type=str,
        default=None,
        help="API URL for the main model",
    )
    parser.add_argument(
        "--model_api_key",
        type=str,
        default=None,
        help="API key for the main model",
    )
    parser.add_argument(
        "--model_temperature",
        type=float,
        default=None,
        help="Temperature for generation (e.g., o3 requires 1.0)",
    )

    # Grounding model configuration (required)
    parser.add_argument(
        "--ground_provider",
        type=str,
        required=True,
        help="Provider for the grounding model",
    )
    parser.add_argument(
        "--ground_url",
        type=str,
        required=True,
        help="URL of the grounding model",
    )
    parser.add_argument(
        "--ground_api_key",
        type=str,
        default=None,
        help="API key for the grounding model",
    )
    parser.add_argument(
        "--ground_model",
        type=str,
        required=True,
        help="Model name for grounding",
    )
    parser.add_argument(
        "--grounding_width",
        type=int,
        required=True,
        help="Width for grounding model screenshots",
    )
    parser.add_argument(
        "--grounding_height",
        type=int,
        required=True,
        help="Height for grounding model screenshots",
    )

    # Agent configuration
    parser.add_argument(
        "--max_trajectory_length",
        type=int,
        default=8,
        help="Maximum image turns to keep in trajectory",
    )
    parser.add_argument(
        "--enable_reflection",
        action="store_true",
        default=True,
        help="Enable reflection agent",
    )
    parser.add_argument(
        "--reflection_frequency",
        type=int,
        default=1,
        help="Reflect every N steps (1=every step)",
    )
    parser.add_argument(
        "--enable_local_env",
        action="store_true",
        default=False,
        help="Enable local coding environment (WARNING: executes arbitrary code)",
    )
    parser.add_argument(
        "--use_robotgo",
        action="store_true",
        default=True,
        help="Use Go robotgo executor instead of pyautogui",
    )

    # Reflection model configuration (optional)
    parser.add_argument(
        "--reflection_provider",
        type=str,
        default="cerebras",
        help="Provider for reflection model",
    )
    parser.add_argument(
        "--reflection_model",
        type=str,
        default="qwen-3-32b",
        help="Model for reflection",
    )
    parser.add_argument(
        "--reflection_url",
        type=str,
        default=None,
        help="URL for reflection model API",
    )
    parser.add_argument(
        "--reflection_api_key",
        type=str,
        default=None,
        help="API key for reflection model",
    )


def cmd_run(args):
    """Execute the run command."""
    # Set up signal handler
    signal.signal(signal.SIGINT, signal_handler)
    
    # Set up logging
    logger = setup_logging()
    
    current_platform = platform.system().lower()

    # Import agent components
    from gui_agents.s3.agents.grounding import OSWorldACI
    from gui_agents.s3.agents.agent_s import AgentS3
    from gui_agents.s3.utils.local_env import LocalEnv

    # Get screen dimensions
    if args.use_robotgo:
        from gui_agents.s3.utils.robotgo_executor import get_screen_size
        screen_width, screen_height = get_screen_size()
    else:
        screen_width, screen_height = pyautogui.size()
    
    scaled_width, scaled_height = scale_screen_dimensions(
        screen_width, screen_height, max_dim_size=2400
    )

    # Configure engines
    engine_params = {
        "engine_type": args.provider,
        "model": args.model,
        "base_url": args.model_url,
        "api_key": args.model_api_key,
        "temperature": args.model_temperature,
    }

    reflection_engine_params = None
    if args.reflection_model or args.reflection_provider:
        reflection_engine_params = {
            "engine_type": args.reflection_provider or args.provider,
            "model": args.reflection_model or args.model,
            "base_url": args.reflection_url or args.model_url,
            "api_key": args.reflection_api_key or args.model_api_key,
            "temperature": args.model_temperature,
        }
        print(f"🔄 Using separate reflection model: {reflection_engine_params['model']}")

    engine_params_for_grounding = {
        "engine_type": args.ground_provider,
        "model": args.ground_model,
        "base_url": args.ground_url,
        "api_key": args.ground_api_key,
        "grounding_width": args.grounding_width,
        "grounding_height": args.grounding_height,
    }

    # Initialize environment
    local_env = None
    if args.enable_local_env:
        print("⚠️  WARNING: Local coding environment enabled. This will execute arbitrary code locally!")
        local_env = LocalEnv()

    grounding_agent = OSWorldACI(
        env=local_env,
        platform=current_platform,
        engine_params_for_generation=engine_params,
        engine_params_for_grounding=engine_params_for_grounding,
        width=screen_width,
        height=screen_height,
    )

    # Validate grounding model
    print("\n🔧 Initializing Agent-S...")
    print(f"📐 Screen size: {screen_width}x{screen_height}")
    print(f"📸 Screenshot size: {scaled_width}x{scaled_height}")
    print(f"🎯 Grounding model config: {args.grounding_width}x{args.grounding_height}")

    if scaled_width != screen_width or scaled_height != screen_height:
        print("⚠️  Screenshots will be scaled down from screen size")

    print("📡 Testing grounding model connectivity...")
    try:
        test_screenshot = pyautogui.screenshot()
        test_screenshot = test_screenshot.resize((scaled_width, scaled_height), Image.LANCZOS)
        buffered = io.BytesIO()
        test_screenshot.save(buffered, format="PNG")
        test_screenshot_bytes = buffered.getvalue()

        grounding_agent.validate_grounding_model(test_screenshot_bytes)
        print("✅ Grounding model ready!")
        print(f"💡 Coordinates will be scaled from {scaled_width}x{scaled_height} → {screen_width}x{screen_height}\n")
    except Exception as e:
        print(f"\n{str(e)}\n")
        return 1

    agent = AgentS3(
        engine_params,
        grounding_agent,
        platform=current_platform,
        max_trajectory_length=args.max_trajectory_length,
        enable_reflection=args.enable_reflection,
        reflection_engine_params=reflection_engine_params,
        reflection_frequency=args.reflection_frequency,
    )

    # Main interaction loop
    while True:
        query = input("Query: ")
        agent.reset()
        run_agent(agent, query, scaled_width, scaled_height, args.use_robotgo)

        response = input("Would you like to provide another query? (y/n): ")
        if response.lower() != "y":
            break

    return 0
