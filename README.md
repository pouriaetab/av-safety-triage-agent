# AV Safety Event Triage Agent

A small demo of applying agentic LLM tool-use to autonomous vehicle
safety incident triage — inspired by [Anthropic's post on using Claude
for CI/CD on-call](https://claude.com/blog/ai-ci-cd-on-call), adapted
from "investigate a build failure" to "investigate a flagged safety
event and produce a severity classification for human review."

## What it does

1. Generates synthetic AV fleet safety events (disengagements,
   near-misses, sensor faults), each with its own perception log,
   planner log, vehicle-state log, and weather conditions — standing
   in for the systems a human investigator would normally check by hand.
2. An LLM agent investigates each event using read-only tools (it can
   fetch logs and search a "lessons learned" file, nothing else), then
   produces a structured severity classification with cited evidence.
3. Writes a SITREP-style markdown report per event and appends a
   summary to a running lessons log, so future events with similar
   root causes surface prior context.
4. Scores the agent's classifications against hidden ground truth
   baked into the synthetic scenarios, so you can see accuracy, not
   just confident-sounding output.

See `examples/` for sample reports and a full terminal run without
needing to execute anything yourself.

## Why this design (read the reasoning, not just the code)

**The agent never decides what counts as an "event."** A deterministic
rule-based layer does that upstream (see the docstring in
`data/generate_events.py`). The agent only investigates things that
already tripped a rule. This mirrors how I'd actually want this to work
in a real safety pipeline — you don't want an LLM's judgment call
standing between a real hazard and an alert firing.

**The agent is read-only.** Its tools can only fetch logs — none of
them can change fleet state, close a ticket, or resolve anything. What
it produces is a recommendation a human reads, never an action taken.

**Severe/critical is hard-gated in code, not just prompted for.** Even
if the model's own JSON output forgot to flag `requires_human_review`,
`triage_agent.py`'s `_parse_final_json` forces it to `true` for
severe/critical regardless of what the model said. Don't rely on a
prompt instruction alone for something safety-relevant if you can
enforce it in code instead.

**Every classification must cite evidence**, and unparseable or
non-converging output is treated as an automatic escalation to human
review (`severity: unknown`, `requires_human_review: true`) rather than
silently defaulting to something that looks fine. A safety-critical
triage system should fail loud, not fail quiet.

**What this agent is *not*:** a replacement for the deterministic
alerting layer, an autonomous decision-maker, or a validated safety
tool. It's a demonstration of applying agentic tool-use to accelerate
the *investigation* step of triage — the same distinction the CI/CD
post draws between detection (deterministic) and investigation
(agentic).

## Running it

**No API key, no cost — verify the plumbing:**
```bash
pip install -r requirements.txt   # anthropic package isn't needed for --mock
python run_demo.py --mock
```
This uses a keyword-matching mock "model" (`agent/mock_client.py`) that
follows the same tool-calling protocol a real LLM would, so you can
confirm the tool loop, the human-review gate, and the reporting all
work — before spending any real tokens. It's explicitly labeled
`[MOCK MODE]` in every output so it's never mistaken for real model
reasoning.

**Real run with Claude:**
```bash
export ANTHROPIC_API_KEY=sk-ant-...
python run_demo.py
```

**Using a free-tier model instead of Claude:** the agent loop, prompt,
tools, and gating logic in `triage_agent.py` are provider-agnostic —
only `_call_model()` and the tool-result plumbing are Anthropic-specific.
To use Gemini's free tier, swap that function for a call to
`genai.GenerativeModel(...).generate_content(...)` with Gemini's
function-calling format, and adapt how tool results get fed back in.
Everything else (prompt, tools, hard-gating, reports) stays the same.

## Project structure
```
data/generate_events.py   synthetic events + per-event log files
agent/tools.py            read-only tool functions + their schema
agent/triage_agent.py     the tool-use loop, prompt, and safety gating
agent/mock_client.py      zero-cost fake model for testing the plumbing
evaluate.py                scores agent output against hidden ground truth
run_demo.py                CLI entry point
examples/                  sample reports + a full sample terminal run
```

## Where I'd take this next

- Real telemetry format instead of synthetic JSON (this is intentionally
  a stand-in for whatever a real fleet's log schema looks like).
- Human-in-the-loop review UI instead of markdown files, so a reviewer
  can approve/reject/redirect the agent's hypothesis and that feedback
  becomes training signal for the lessons log.
- Multi-agent investigation (parallel sub-agents per data source,
  synthesized by an orchestrator) for events with many log sources —
  overkill for this scope, but the pattern from the CI/CD post.
- A companion statistical layer for aggregate severity-distribution
  analysis across many triaged events (see my related work on
  extreme-value bias in pooled near-miss severity data).
