"""
Entry point for the demo.

    python run_demo.py --mock          # no API key needed, verifies plumbing
    python run_demo.py                 # real Claude, needs ANTHROPIC_API_KEY
    python run_demo.py --n 3           # only run 3 events instead of all 5

Each run: generates synthetic events -> triages each one with the agent ->
writes a SITREP markdown report per event to reports/ -> prints a summary
table -> scores against ground truth (evaluate.py) so you can see how
often the agent's classification matched the hidden scenario design.
"""
import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from data.generate_events import generate_events
from agent.triage_agent import triage_event, write_report, append_lesson
from evaluate import score_results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mock", action="store_true",
                         help="Use the mock client (no API calls, no tokens spent).")
    parser.add_argument("--n", type=int, default=5, help="Number of events to generate.")
    parser.add_argument("--model", default="claude-sonnet-4-6",
                         help="Model name (only used in real mode).")
    args = parser.parse_args()

    print(f"Generating {args.n} synthetic safety events...")
    events = generate_events(n=args.n)

    if args.mock:
        from agent.mock_client import MockAnthropicClient
        client = MockAnthropicClient()
        print("Running in MOCK mode -- no API calls, no tokens spent.\n")
    else:
        try:
            import anthropic
        except ImportError:
            print("The 'anthropic' package isn't installed. Run:\n"
                  "  pip install -r requirements.txt\n"
                  "or use --mock to test the plumbing without it.")
            sys.exit(1)
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            print("ANTHROPIC_API_KEY is not set. Either:\n"
                  "  export ANTHROPIC_API_KEY=sk-...\n"
                  "or run with --mock to test without an API key.")
            sys.exit(1)
        client = anthropic.Anthropic(api_key=api_key)
        print(f"Running with real model: {args.model}\n")

    results = []
    for event in events:
        print(f"Investigating {event['event_id']} ({event['event_type']} @ {event['road_type']})...")
        result = triage_event(event, client, model=args.model, verbose=True)
        write_report(result, event)
        append_lesson(result, event)
        results.append((event, result))
        print(f"    -> severity={result['severity']}  human_review={result['requires_human_review']}\n")

    print("\n=== Summary ===")
    print(f"{'event_id':16s} {'type':16s} {'severity':10s} {'review?':8s}")
    for event, result in results:
        print(f"{result['event_id']:16s} {event['event_type']:16s} "
              f"{result['severity']:10s} {str(result['requires_human_review']):8s}")

    print("\n=== Scoring vs. hidden ground truth ===")
    score_results(results)

    print(f"\nReports written to: {Path('reports').resolve()}")
    print(f"Lessons log: {Path('lessons.md').resolve()}")


if __name__ == "__main__":
    main()
