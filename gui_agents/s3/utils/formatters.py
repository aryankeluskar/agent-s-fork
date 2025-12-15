"""This file contains various formatting checks used to reprompt an agent for correctly formatted responses."""

import re
from gui_agents.s3.utils.common_utils import (
    extract_agent_functions,
    parse_code_from_string,
    create_pyautogui_code,
    split_thinking_response,
)

def single_action_check(response):
    """Check that there's exactly ONE code block with ONE agent function in the entire response.

    This prevents the LLM from generating multiple future steps in a single response.
    """
    # Find ALL code blocks in the response
    pattern = r"```(?:\w+\s+)?(.*?)```"
    all_matches = re.findall(pattern, response, re.DOTALL)

    # Reject if there's more than one code block
    if len(all_matches) != 1:
        return False

    # Check that the single code block has exactly one agent function
    code = all_matches[0]
    agent_functions = extract_agent_functions(code)
    return len(agent_functions) == 1

single_action_error_msg = (
    "Incorrect code: There must be exactly ONE code block with a single agent action. "
    "Do not generate multiple future steps - only return the immediate next action."
)
SINGLE_ACTION_FORMATTER = lambda response: (
    single_action_check(response),
    single_action_error_msg,
)


def _attempt_code_creation(agent, code, obs):
    """Attempts to create a pyautogui code snippet from the response code"""
    try:
        return create_pyautogui_code(agent, code, obs)
    except Exception as e:
        return None


code_valid_check = (
    lambda agent, obs, response: _attempt_code_creation(
        agent, parse_code_from_string(response), obs
    )
    is not None
)
code_valid_error_msg = "Incorrect code: The agent action must be a valid function and use valid parameters from the docstring list."
CODE_VALID_FORMATTER = lambda agent, obs, response: (
    code_valid_check(agent, obs, response),
    code_valid_error_msg,
)

thoughts_answer_tag_check = lambda response: split_thinking_response(response)[1] != ""
thoughts_answer_tag_error_msg = "Incorrect response: The response must contain both <thoughts>...</thoughts> and <answer>...</answer> tags."
THOUGHTS_ANSWER_TAG_FORMATTER = lambda response: (
    thoughts_answer_tag_check(response),
    thoughts_answer_tag_error_msg,
)

integer_answer_check = (
    lambda response: split_thinking_response(response)[0].strip().isdigit()
)
integer_answer_error_msg = (
    "Incorrect response: The <answer>...</answer> tag must contain a single integer."
)
INTEGER_ANSWER_FORMATTER = lambda response: (
    integer_answer_check(response),
    integer_answer_error_msg,
)
