# Architecture

```
                    ┌─────────────────────────────┐
                    │  Deterministic monitoring    │
                    │  (rule-based, NOT this repo) │
                    │  decides: is this an event?  │
                    └──────────────┬───────────────┘
                                   │ event flagged
                                   ▼
                    ┌─────────────────────────────┐
                    │      Triage Agent            │
                    │  (agent/triage_agent.py)     │
                    │                               │
                    │  loop:                        │
                    │   - call tools to gather      │
                    │     evidence                  │
                    │   - reason over results        │
                    │   - repeat until confident      │
                    └──────────────┬───────────────┘
                                   │ tool calls (read-only)
                 ┌─────────────────┼──────────────────┬──────────────┐
                 ▼                 ▼                  ▼              ▼
          perception_log     planner_log       vehicle_state     weather
                                                                       │
                                                              also: search_lessons
                                                              (past root causes)
                                   │
                                   ▼
                    ┌─────────────────────────────┐
                    │   Final JSON classification   │
                    │   severity / root_cause /      │
                    │   evidence / confidence         │
                    └──────────────┬───────────────┘
                                   │
                       ┌───────────┴────────────┐
                       ▼                         ▼
              severity in                 severity NOT in
              {severe, critical}          {severe, critical}
                       │                         │
                       ▼                         ▼
        requires_human_review = True     recorded, no mandatory
        (enforced in code, not          gate — still visible in
         just prompted for)              SITREP + lessons log
                       │                         │
                       └───────────┬─────────────┘
                                   ▼
                    ┌─────────────────────────────┐
                    │  SITREP markdown report      │
                    │  + lessons.md append          │
                    └─────────────────────────────┘
```

## Why the hard gate matters

The prompt already tells the model to flag severe/critical events for
mandatory review. But a prompt instruction is a request, not a
guarantee — models occasionally forget instructions, especially ones
buried in a long system prompt. `triage_agent.py`'s
`_parse_final_json()` re-checks the model's own `severity` field after
parsing and forces `requires_human_review = True` whenever severity is
severe/critical, regardless of what the model output for that field.

This is a small thing in a demo, but it's the kind of design decision
worth being able to explain: in a safety-critical pipeline, anything
you can enforce deterministically in code instead of relying on model
compliance, you should.
