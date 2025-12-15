import argparse
import datetime
import io
import logging
import os
import platform
import pyautogui
import signal
import sys
import time

from PIL import Image

from gui_agents.s3.agents.grounding import OSWorldACI
from gui_agents.s3.agents.agent_s import AgentS3
from gui_agents.s3.utils.local_env import LocalEnv

current_platform = platform.system().lower()

# Global flag to track pause state for debugging
paused = False


def get_char():
    """Get a single character from stdin without pressing Enter"""
    try:
        # Import termios and tty on Unix-like systems
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
            # Windows fallback
            import msvcrt

            return msvcrt.getch().decode("utf-8", errors="ignore")
    except:
        return input()  # Fallback for non-terminal environments


def signal_handler(signum, frame):
    """Handle Ctrl+C signal for debugging during agent execution"""
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
        # Already paused, second Ctrl+C means quit
        print("\n\n🛑 Exiting Agent-S...")
        sys.exit(0)


# Set up signal handler for Ctrl+C
signal.signal(signal.SIGINT, signal_handler)

logger = logging.getLogger()
logger.setLevel(logging.DEBUG)

datetime_str: str = datetime.datetime.now().strftime("%Y%m%d@%H%M%S")

log_dir = "logs"
os.makedirs(log_dir, exist_ok=True)

file_handler = logging.FileHandler(
    os.path.join("logs", "normal-{:}.log".format(datetime_str)), encoding="utf-8"
)
debug_handler = logging.FileHandler(
    os.path.join("logs", "debug-{:}.log".format(datetime_str)), encoding="utf-8"
)
stdout_handler = logging.StreamHandler(sys.stdout)
sdebug_handler = logging.FileHandler(
    os.path.join("logs", "sdebug-{:}.log".format(datetime_str)), encoding="utf-8"
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

platform_os = platform.system()


def show_permission_dialog(code: str, action_description: str):
    """Show a platform-specific permission dialog and return True if approved."""
    if platform.system() == "Darwin":
        result = os.system(
            f'osascript -e \'display dialog "Do you want to execute this action?\n\n{code} which will try to {action_description}" with title "Action Permission" buttons {{"Cancel", "OK"}} default button "OK" cancel button "Cancel"\''
        )
        return result == 0
    elif platform.system() == "Linux":
        result = os.system(
            f'zenity --question --title="Action Permission" --text="Do you want to execute this action?\n\n{code}" --width=400 --height=200'
        )
        return result == 0
    return False


def scale_screen_dimensions(width: int, height: int, max_dim_size: int):
    scale_factor = min(max_dim_size / width, max_dim_size / height, 1)
    safe_width = int(width * scale_factor)
    safe_height = int(height * scale_factor)
    return safe_width, safe_height


def run_agent(agent, instruction: str, scaled_width: int, scaled_height: int, use_robotgo: bool = False):
    from gui_agents.s3.utils.profiler import profiler

    global paused
    obs = {}
    traj = "Task:\n" + instruction
    subtask_traj = ""

    # Reset profiler for new task
    profiler.reset()

    for step in range(15):
        with profiler.profile(f"Step_{step+1}"):
            # Check if we're in paused state and wait
            while paused:
                time.sleep(0.1)

            # Get screen shot using mss (faster than pyautogui)
            with profiler.profile("Screenshot_Capture"):
                # OPTIMIZATION: Use mss library instead of pyautogui (3-5x faster)
                import mss
                with mss.mss() as sct:
                    # Capture the first monitor (primary screen)
                    monitor = sct.monitors[1]
                    sct_img = sct.grab(monitor)
                    # Convert mss screenshot to PIL Image
                    screenshot = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")

                # OPTIMIZATION: Use BICUBIC interpolation instead of LANCZOS (2-3x faster, minimal quality loss)
                screenshot = screenshot.resize((scaled_width, scaled_height), Image.BICUBIC)

                # Compress screenshot using WebP format for faster LLM processing
                from gui_agents.s3.utils.common_utils import compress_image
                screenshot_bytes = compress_image(image=screenshot)

                # Convert to base64 string.
                obs["screenshot"] = screenshot_bytes

            # Check again for pause state before prediction
            while paused:
                time.sleep(0.1)

            print(f"\n🔄 Step {step + 1}/15: Getting next action from agent...")

            # Get next action code from the agent
            with profiler.profile("Agent_Prediction"):
                info, code = agent.predict(instruction=instruction, observation=obs)

            if "done" in code[0].lower() or "fail" in code[0].lower():
                # Log completion for debugging
                logger.info(
                    f"Agent completed task on step {step + 1}. Code: {code[0]}"
                )

                if platform.system() == "Darwin":
                    os.system(
                        'osascript -e \'display dialog "Task Completed" with title "OpenACI Agent" buttons "OK" default button "OK"\''
                    )
                elif platform.system() == "Linux":
                    os.system(
                        'zenity --info --title="OpenACI Agent" --text="Task Completed" --width=200 --height=100'
                    )

                break

            if "next" in code[0].lower():
                continue

            if "wait" in code[0].lower():
                print("⏳ Agent requested wait...")
                time.sleep(5)
                continue

            else:
                time.sleep(1.0)
                print("EXECUTING CODE:", code[0])

                # Check for pause state before execution
                while paused:
                    time.sleep(0.1)

                # Execute code using robotgo or pyautogui
                with profiler.profile("Code_Execution"):
                    if use_robotgo:
                        from gui_agents.s3.utils.robotgo_executor import execute_robotgo_code
                        success = execute_robotgo_code(code[0])
                        if not success:
                            logger.error("Failed to execute robotgo code")
                    else:
                        exec(code[0])
                time.sleep(1.0)

                # Update task and subtask trajectories
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
            time_saved = grounding_agent._cache_hits * 1.3  # Assume ~1.3s per cached call
            print("\n" + "="*100)
            print("GROUNDING CACHE STATISTICS")
            print("="*100)
            print(f"Cache Hits:       {grounding_agent._cache_hits}")
            print(f"Cache Misses:     {grounding_agent._cache_misses}")
            print(f"Total Calls:      {total_calls}")
            print(f"Hit Rate:         {hit_rate:.1f}%")
            print(f"Est. Time Saved:  ~{time_saved:.1f}s")
            print("="*100 + "\n")

    # Generate and display profiling summary
    summary = profiler.generate_summary()
    logger.info(summary)
    print(summary)


def main():
    parser = argparse.ArgumentParser(description="Run AgentS3 with specified model.")
    parser.add_argument(
        "--provider",
        type=str,
        default="openai",
        help="Specify the provider to use (e.g., openai, anthropic, etc.). IMPORTANT: Must support vision/multimodal for GUI agents.",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="gpt-5.2-2025-12-11",
        help="Specify the model to use (e.g., gpt-5.2-2025-12-11)",
    )
    parser.add_argument(
        "--model_url",
        type=str,
        default=None,
        help="The URL of the main generation model API.",
    )
    parser.add_argument(
        "--model_api_key",
        type=str,
        default=None,
        help="The API key of the main generation model.",
    )
    parser.add_argument(
        "--model_temperature",
        type=float,
        default=None,
        help="Temperature to fix the generation model at (e.g. o3 can only be run with 1.0)",
    )

    # Grounding model config: Self-hosted endpoint based (required)
    parser.add_argument(
        "--ground_provider",
        type=str,
        required=True,
        help="The provider for the grounding model",
    )
    parser.add_argument(
        "--ground_url",
        type=str,
        required=True,
        help="The URL of the grounding model",
    )
    parser.add_argument(
        "--ground_api_key",
        type=str,
        default=None,
        help="The API key of the grounding model.",
    )
    parser.add_argument(
        "--ground_model",
        type=str,
        required=True,
        help="The model name for the grounding model",
    )
    parser.add_argument(
        "--grounding_width",
        type=int,
        required=True,
        help="Width of screenshot image after processor rescaling",
    )
    parser.add_argument(
        "--grounding_height",
        type=int,
        required=True,
        help="Height of screenshot image after processor rescaling",
    )

    # AgentS3 specific arguments
    parser.add_argument(
        "--max_trajectory_length",
        type=int,
        default=8,
        help="Maximum number of image turns to keep in trajectory",
    )
    parser.add_argument(
        "--enable_reflection",
        action="store_true",
        default=True,
        help="Enable reflection agent to assist the worker agent",
    )
    parser.add_argument(
        "--reflection_frequency",
        type=int,
        default=1,
        help="Reflection frequency: reflect every N steps (1=every step, 2=every other step, etc.). Higher values skip more reflections for speed.",
    )
    parser.add_argument(
        "--enable_local_env",
        action="store_true",
        default=False,
        help="Enable local coding environment for code execution (WARNING: Executes arbitrary code locally)",
    )
    parser.add_argument(
        "--use_robotgo",
        action="store_true",
        default=False,
        help="Use Go robotgo executor instead of Python pyautogui (requires robotgo_executor binary)",
    )

    # Reflection model config (optional - defaults to main model if not specified)
    parser.add_argument(
        "--reflection_provider",
        type=str,
        default="cerebras",
        help="Provider for reflection model (e.g., cerebras, openai, anthropic). Default: cerebras.",
    )
    parser.add_argument(
        "--reflection_model",
        type=str,
        default="qwen-3-32b",
        help="Faster/cheaper model for reflection (e.g., qwen-3-32b for Cerebras, gpt-4o-mini for OpenAI, claude-3-5-haiku-20241022 for Anthropic). Default: qwen-3-32b.",
    )
    parser.add_argument(
        "--reflection_url",
        type=str,
        default=None,
        help="URL for reflection model API. If not set, uses main model URL.",
    )
    parser.add_argument(
        "--reflection_api_key",
        type=str,
        default=None,
        help="API key for reflection model. If not set, uses main model API key.",
    )

    args = parser.parse_args()

    # Re-scales screenshot size to ensure it fits in UI-TARS context limit
    if args.use_robotgo:
        from gui_agents.s3.utils.robotgo_executor import get_screen_size
        screen_width, screen_height = get_screen_size()
    else:
        screen_width, screen_height = pyautogui.size()
    scaled_width, scaled_height = scale_screen_dimensions(
        screen_width, screen_height, max_dim_size=2400
    )

    # Load the general engine params
    engine_params = {
        "engine_type": args.provider,
        "model": args.model,
        "base_url": args.model_url,
        "api_key": args.model_api_key,
        "temperature": getattr(args, "model_temperature", None),
    }

    # Load reflection engine params (optional - defaults to main engine)
    reflection_engine_params = None
    if args.reflection_model or args.reflection_provider:
        reflection_engine_params = {
            "engine_type": args.reflection_provider or args.provider,
            "model": args.reflection_model or args.model,
            "base_url": args.reflection_url or args.model_url,
            "api_key": args.reflection_api_key or args.model_api_key,
            "temperature": getattr(args, "model_temperature", None),
        }
        print(f"🔄 Using separate reflection model: {reflection_engine_params['model']}")

    # Load the grounding engine from a custom endpoint
    engine_params_for_grounding = {
        "engine_type": args.ground_provider,
        "model": args.ground_model,
        "base_url": args.ground_url,
        "api_key": args.ground_api_key,
        "grounding_width": args.grounding_width,
        "grounding_height": args.grounding_height,
    }

    # Initialize environment based on user preference
    local_env = None
    if args.enable_local_env:
        print(
            "⚠️  WARNING: Local coding environment enabled. This will execute arbitrary code locally!"
        )
        local_env = LocalEnv()

    grounding_agent = OSWorldACI(
        env=local_env,
        platform=current_platform,
        engine_params_for_generation=engine_params,
        engine_params_for_grounding=engine_params_for_grounding,
        width=screen_width,
        height=screen_height,
    )

    # Validate grounding model connectivity before starting
    print("\n🔧 Initializing Agent-S...")
    print(f"📐 Screen size: {screen_width}x{screen_height}")
    print(f"📸 Screenshot size: {scaled_width}x{scaled_height}")
    print(f"🎯 Grounding model config: {args.grounding_width}x{args.grounding_height}")

    if scaled_width != screen_width or scaled_height != screen_height:
        print("⚠️  Screenshots will be scaled down from screen size")

    print("📡 Testing grounding model connectivity...")
    try:
        # Take a test screenshot for validation
        if args.use_robotgo:
            # Still use pyautogui for screenshots (or could use mss)
            test_screenshot = pyautogui.screenshot()
        else:
            test_screenshot = pyautogui.screenshot()
        test_screenshot = test_screenshot.resize((scaled_width, scaled_height), Image.LANCZOS)
        buffered = io.BytesIO()
        test_screenshot.save(buffered, format="PNG")
        test_screenshot_bytes = buffered.getvalue()

        # Validate the grounding model
        grounding_agent.validate_grounding_model(test_screenshot_bytes)
        print("✅ Grounding model ready!")
        print(f"💡 Coordinates will be scaled from {scaled_width}x{scaled_height} → {screen_width}x{screen_height}\n")
    except Exception as e:
        print(f"\n{str(e)}\n")
        sys.exit(1)

    agent = AgentS3(
        engine_params,
        grounding_agent,
        platform=current_platform,
        max_trajectory_length=args.max_trajectory_length,
        enable_reflection=args.enable_reflection,
        reflection_engine_params=reflection_engine_params,
        reflection_frequency=args.reflection_frequency,
    )

    while True:
        query = input("Query: ")

        agent.reset()

        # Run the agent on your own device
        run_agent(agent, query, scaled_width, scaled_height)

        response = input("Would you like to provide another query? (y/n): ")
        if response.lower() != "y":
            break


if __name__ == "__main__":
    main()
