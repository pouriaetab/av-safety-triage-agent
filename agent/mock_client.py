"""
A fake "model" that follows the same tool-calling protocol as the
Anthropic client, so you can run the full agent loop end-to-end with
zero API calls and zero cost.

This is NOT a stand-in for real agent reasoning -- it uses dumb keyword
matching instead of an LLM. Its only purpose is to let you verify the
plumbing (does the loop call tools correctly, parse results correctly,
hit the human-review gate correctly) before you spend real tokens.
Run with real Claude or Gemini for anything you'd actually show as
agent output quality.

Use it with: python run_demo.py --mock
"""
import json
from types import SimpleNamespace


class MockBlock(SimpleNamespace):
    pass


class MockResponse(SimpleNamespace):
    pass


class MockMessages:
    def create(self, model, max_tokens, system, tools, messages):
        n_user_turns = sum(1 for m in messages if m["role"] == "user")

        if n_user_turns == 1:
            # First turn: request the core evidence in one batch.
            event_id = _extract_event_id(messages)
            blocks = [
                MockBlock(type="tool_use", id="call_1", name="get_perception_log",
                          input={"event_id": event_id}),
                MockBlock(type="tool_use", id="call_2", name="get_planner_log",
                          input={"event_id": event_id}),
                MockBlock(type="tool_use", id="call_3", name="get_vehicle_state",
                          input={"event_id": event_id}),
                MockBlock(type="tool_use", id="call_4", name="get_weather",
                          input={"event_id": event_id}),
            ]
            return MockResponse(content=blocks)

        if n_user_turns == 2:
            # Second turn: do one lessons-log search, then converge.
            combined = _combined_tool_text(messages)
            keyword = "glare" if "glare" in combined else (
                "rain" if "rain" in combined else "fault")
            return MockResponse(content=[
                MockBlock(type="tool_use", id="call_5", name="search_lessons",
                          input={"keywords": keyword}),
            ])

        # Third turn: produce the final classification from simple keyword rules.
        event_id = _extract_event_id(messages)
        combined = _combined_tool_text(messages)
        severity, root_cause, evidence = _classify(combined)
        result = {
            "event_id": event_id,
            "severity": severity,
            "confidence": 0.6,
            "root_cause": root_cause,
            "evidence": evidence,
            "requires_human_review": severity in ("severe", "critical"),
            "reasoning_summary": (
                "[MOCK MODE - keyword heuristic, not real model reasoning] "
                f"Classified as {severity} based on keyword matches in tool output."
            ),
        }
        return MockResponse(content=[MockBlock(type="text", text=json.dumps(result))])


class MockAnthropicClient:
    def __init__(self):
        self.messages = MockMessages()


def _extract_event_id(messages):
    first_user_text = messages[0]["content"]
    # "Investigate event EVT-xxxxxxxx." -- pull the token starting with EVT-
    for token in first_user_text.replace(".", " ").split():
        if token.startswith("EVT-"):
            return token
    return "UNKNOWN"


def _combined_tool_text(messages):
    parts = []
    for m in messages:
        if m["role"] == "user" and isinstance(m["content"], list):
            for block in m["content"]:
                if isinstance(block, dict) and block.get("type") == "tool_result":
                    parts.append(str(block.get("content", "")))
    return " ".join(parts).lower()


def _classify(combined_text):
    if "pedestrian" in combined_text or "closing speed" in combined_text or "abort" in combined_text:
        return (
            "severe",
            "Detection degraded under adverse conditions, reducing safety margin close to threshold.",
            ["Perception/planner logs show degraded detection range or timing under adverse weather.",
             "Vehicle state shows an aggressive/emergency maneuver was required."],
        )
    if "flicker" in combined_text or "hard brake" in combined_text:
        return (
            "moderate",
            "Transient perception confidence dip led to a precautionary planner correction.",
            ["Perception log shows a confidence drop on a tracked object.",
             "Vehicle state shows moderate deceleration with no contact."],
        )
    return (
        "minor",
        "Transient sensor or classification issue with no resulting hazard.",
        ["Vehicle state shows no maneuver or no hazard resulted.",
         "Redundant sensing or planner fallback handled the anomaly as designed."],
    )
