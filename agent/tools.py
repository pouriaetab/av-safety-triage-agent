"""
Tool functions exposed to the LLM agent. Each one reads a single data
source for a given event_id -- this mirrors how a human investigator
would pull perception logs, planner logs, vehicle state, and weather
from separate systems rather than having it all pre-joined for them.

Keeping these as plain read-only functions (no side effects) means the
agent can never do anything except gather evidence and write its own
report -- it can't touch fleet state, close tickets, or take action.
That boundary is deliberate: see README "What this agent is not".
"""
import json
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"
LOGS_DIR = DATA_DIR / "logs"
LESSONS_PATH = DATA_DIR.parent / "lessons.md"


def get_perception_log(event_id: str) -> str:
    return _read_log(event_id, "perception_log.json")


def get_planner_log(event_id: str) -> str:
    return _read_log(event_id, "planner_log.json")


def get_vehicle_state(event_id: str) -> str:
    return _read_log(event_id, "vehicle_state.json")


def get_weather(event_id: str) -> str:
    return _read_log(event_id, "weather.json")


def search_lessons(keywords: str) -> str:
    """Search past triage summaries for similar prior events."""
    if not LESSONS_PATH.exists():
        return "No prior lessons recorded yet."
    text = LESSONS_PATH.read_text()
    keyword_list = [k.strip().lower() for k in keywords.split(",") if k.strip()]
    if not keyword_list:
        return "No keywords provided."
    matches = []
    for block in text.split("\n---\n"):
        if any(k in block.lower() for k in keyword_list):
            matches.append(block.strip())
    if not matches:
        return f"No prior lessons matched keywords: {keywords}"
    return "\n\n".join(matches[-3:])  # most recent 3 matches


def _read_log(event_id: str, filename: str) -> str:
    path = LOGS_DIR / event_id / filename
    if not path.exists():
        return f"No {filename} found for {event_id}."
    return path.read_text()


# Tool schema in Anthropic Messages API format.
TOOL_DEFINITIONS = [
    {
        "name": "get_perception_log",
        "description": "Retrieve the perception-stack log note for a given event (object detection, tracking, sensor confidence).",
        "input_schema": {
            "type": "object",
            "properties": {"event_id": {"type": "string"}},
            "required": ["event_id"],
        },
    },
    {
        "name": "get_planner_log",
        "description": "Retrieve the motion-planner log note for a given event (what maneuver was planned/executed and why).",
        "input_schema": {
            "type": "object",
            "properties": {"event_id": {"type": "string"}},
            "required": ["event_id"],
        },
    },
    {
        "name": "get_vehicle_state",
        "description": "Retrieve vehicle state at the time of the event (braking, deceleration, contact, lane departure).",
        "input_schema": {
            "type": "object",
            "properties": {"event_id": {"type": "string"}},
            "required": ["event_id"],
        },
    },
    {
        "name": "get_weather",
        "description": "Retrieve weather and road-type conditions at the time of the event.",
        "input_schema": {
            "type": "object",
            "properties": {"event_id": {"type": "string"}},
            "required": ["event_id"],
        },
    },
    {
        "name": "search_lessons",
        "description": "Search the lessons-learned log for prior events with similar root causes. Pass comma-separated keywords (e.g. 'glare, perception confidence').",
        "input_schema": {
            "type": "object",
            "properties": {"keywords": {"type": "string"}},
            "required": ["keywords"],
        },
    },
]

TOOL_FUNCTIONS = {
    "get_perception_log": get_perception_log,
    "get_planner_log": get_planner_log,
    "get_vehicle_state": get_vehicle_state,
    "get_weather": get_weather,
    "search_lessons": search_lessons,
}
