"""
Compares the agent's severity classification against the hidden
ground truth baked into data/generate_events.py's scenarios.

This exists because "the agent produced a confident-sounding answer"
and "the agent was right" are different claims, and a safety-critical
demo should show you're checking the second one, not just the first.
"""

SEVERITY_ORDER = ["minor", "moderate", "severe", "critical"]


def score_results(results):
    correct = 0
    off_by_one_understated = 0
    total = len(results)

    for event, result in results:
        truth = event.get("_ground_truth_severity", "unknown")
        predicted = result.get("severity", "unknown")
        match = "MATCH" if predicted == truth else "MISMATCH"
        if predicted == truth:
            correct += 1
        elif _severity_index(predicted) < _severity_index(truth):
            off_by_one_understated += 1
            match = "MISMATCH (understated -- worth flagging)"

        print(f"{result['event_id']:16s} predicted={predicted:10s} truth={truth:10s}  {match}")

    print(f"\n{correct}/{total} exact matches.")
    if off_by_one_understated:
        print(f"{off_by_one_understated} event(s) where the agent UNDERSTATED severity "
              f"relative to ground truth -- in a real pipeline this is the failure "
              f"mode that matters most, since overstating just costs a human review "
              f"cycle, but understating risks a real issue getting closed too early.")


def _severity_index(level):
    try:
        return SEVERITY_ORDER.index(level)
    except ValueError:
        return -1  # unknown/unparsed treated as worst case for comparison purposes
