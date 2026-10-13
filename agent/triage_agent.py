"""
The triage agent itself.

Design intent (this is the part worth being able to explain clearly,
not just the code):

1. This agent NEVER decides whether an event is worth investigating.
   That decision already happened upstream, deterministically (see
   data/generate_events.py's docstring). The agent only investigates
   events that were already flagged by a rule-based system.

2. The agent is read-only. Its tools (agent/tools.py) can only fetch
   logs -- none of them can change fleet state, close an incident, or
   trigger a rollback. Whatever it concludes is a *recommendation*
   that a human safety reviewer reads, not an action.

3. Severe/critical classifications are hard-gated for mandatory human
   review -- the agent cannot mark them resolved or downgrade them.
   This mirrors real safety-review practice: automation can accelerate
   investigation, but sign-off on anything safety-critical stays human.

4. Every classification must cite which tool outputs it relied on.
   An unsupported severity judgment is treated as a failure of the
   agent, not a stylistic nitpick -- see evaluate.py.

Swapping providers: this file isolates all Anthropic-specific code in
`_call_model()` and `_run_tool_call()`. To use Gemini's free tier
instead, you'd replace `_call_model` with a call to
`genai.GenerativeModel(...).generate_content(..., tools=[...])` and
adapt the tool-call/tool-result plumbing to Gemini's function-calling
format. The rest of the agent (prompt, tool functions, gating logic,
report writer) does not need to change.
"""
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from agent.tools import TOOL_DEFINITIONS, TOOL_FUNCTIONS, LESSONS_PATH

REPORTS_DIR = Path(__file__).parent.parent / "reports"
REPORTS_DIR.mkdir(exist_ok=True)

SEVERITY_LEVELS = ["minor", "moderate", "severe", "critical"]
MANDATORY_REVIEW_LEVELS = {"severe", "critical"}

SYSTEM_PROMPT = """You are a safety-event triage assistant for an autonomous vehicle fleet.

An event has already been flagged by a deterministic monitoring system
(a disengagement, near-miss, or sensor fault). Your job is to investigate
using the tools available, form a root-cause hypothesis, and classify
severity. You do NOT decide what counts as an event -- that already happened.
You do NOT take any action -- you only produce a recommendation for a human
safety reviewer.

Rules you must follow:
1. Use the available tools to gather evidence before concluding anything.
   Pull perception, planner, and vehicle state logs at minimum. Check weather
   if conditions could be a factor. Search past lessons for similar patterns.
2. Every claim in your final classification must be traceable to a specific
   tool result. If you are not confident, say so explicitly rather than
   guessing.
3. Classify severity as one of: minor, moderate, severe, critical.
4. If you classify something as severe or critical, you must say explicitly
   that it requires mandatory human safety-review sign-off before closure --
   you are not authorized to consider it resolved.
5. Return your final answer as a single JSON object (no other prose) with
   these exact keys: event_id, severity, confidence (0-1), root_cause,
   evidence (list of short strings, each citing a tool result), 
   requires_human_review (bool), reasoning_summary (2-3 sentences).
"""


def triage_event(event: dict, client, model: str = "claude-sonnet-4-6",
                  max_turns: int = 6, verbose: bool = True) -> dict:
    """
    Runs the tool-use loop for a single event and returns the parsed
    JSON classification. `client` is an Anthropic client instance.
    """
    event_id = event["event_id"]
    messages = [{
        "role": "user",
        "content": (
            f"Investigate event {event_id}.\n"
            f"Known metadata: type={event['event_type']}, "
            f"road_type={event['road_type']}, weather={event['weather']}, "
            f"timestamp={event['timestamp']}.\n"
            f"Use your tools to gather evidence, then return the final JSON classification."
        ),
    }]

    for turn in range(max_turns):
        response = _call_model(client, model, messages)

        tool_calls = [b for b in response.content if b.type == "tool_use"]
        text_blocks = [b for b in response.content if b.type == "text"]

        if verbose and text_blocks:
            for tb in text_blocks:
                if tb.text.strip():
                    print(f"    [agent reasoning] {tb.text.strip()[:200]}")

        if not tool_calls:
            # Model returned its final answer with no more tool calls.
            final_text = "".join(tb.text for tb in text_blocks)
            return _parse_final_json(final_text, event_id)

        messages.append({"role": "assistant", "content": response.content})

        tool_results = []
        for call in tool_calls:
            if verbose:
                print(f"    [tool call] {call.name}({call.input})")
            result = _run_tool_call(call.name, call.input)
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": call.id,
                "content": result,
            })
        messages.append({"role": "user", "content": tool_results})

    return {
        "event_id": event_id,
        "severity": "unknown",
        "confidence": 0.0,
        "root_cause": "Agent did not converge within max_turns.",
        "evidence": [],
        "requires_human_review": True,
        "reasoning_summary": "Escalated to human review: agent failed to produce a final classification.",
    }


def _call_model(client, model, messages):
    return client.messages.create(
        model=model,
        max_tokens=1500,
        system=SYSTEM_PROMPT,
        tools=TOOL_DEFINITIONS,
        messages=messages,
    )


def _run_tool_call(name, tool_input):
    fn = TOOL_FUNCTIONS.get(name)
    if fn is None:
        return f"Unknown tool: {name}"
    try:
        return fn(**tool_input)
    except Exception as e:
        return f"Tool error: {e}"


def _parse_final_json(text, event_id):
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
    try:
        result = json.loads(text)
    except json.JSONDecodeError:
        # Fail safe: if the agent didn't return clean JSON, escalate rather
        # than silently guessing at a severity.
        result = {
            "event_id": event_id,
            "severity": "unknown",
            "confidence": 0.0,
            "root_cause": "Could not parse agent output as JSON.",
            "evidence": [],
            "requires_human_review": True,
            "reasoning_summary": f"Escalated: unparseable agent output: {text[:300]}",
        }

    # Hard gate, enforced in code, not just prompted for: any severe/critical
    # classification MUST require human review, regardless of what the model said.
    if result.get("severity") in MANDATORY_REVIEW_LEVELS:
        result["requires_human_review"] = True

    return result


def append_lesson(result: dict, event: dict):
    """Append a short summary to the running lessons log for future retrieval."""
    entry = (
        f"event_id: {result.get('event_id')}\n"
        f"type: {event.get('event_type')} | road: {event.get('road_type')} | "
        f"weather: {event.get('weather')}\n"
        f"severity: {result.get('severity')} | root_cause: {result.get('root_cause')}\n"
        f"logged: {datetime.now(timezone.utc).isoformat()}"
    )
    with open(LESSONS_PATH, "a") as f:
        f.write(entry + "\n---\n")


def write_report(result: dict, event: dict) -> Path:
    """Writes a SITREP-style markdown report for a single event."""
    path = REPORTS_DIR / f"{result['event_id']}_sitrep.md"
    review_flag = "**REQUIRES HUMAN SAFETY REVIEW**" if result.get("requires_human_review") else "No mandatory review flag"
    content = f"""# Safety Event SITREP: {result['event_id']}

**Event type:** {event['event_type']}
**Road type:** {event['road_type']}
**Weather:** {event['weather']}
**Timestamp:** {event['timestamp']}

## Agent Classification
- **Severity:** {result.get('severity', 'unknown')}
- **Confidence:** {result.get('confidence', 'n/a')}
- **Review status:** {review_flag}

## Root Cause Hypothesis
{result.get('root_cause', 'n/a')}

## Supporting Evidence
{chr(10).join('- ' + e for e in result.get('evidence', [])) or '- none provided'}

## Reasoning Summary
{result.get('reasoning_summary', 'n/a')}

---
*Generated by an LLM triage agent. This is a recommendation for human safety-review, not a resolution.*
"""
    path.write_text(content)
    return path
