"""
Generates synthetic AV fleet safety events + the raw log sources an
investigator would normally pull by hand: perception log, planner log,
vehicle state, and weather.

This stands in for what a deterministic alerting layer would have
already flagged (a disengagement, a near-miss, a sensor fault). The
agent's job starts AFTER this point -- it never decides what counts
as an event, it only investigates events that already fired.
"""
import json
import random
import uuid
from datetime import datetime, timedelta
from pathlib import Path

random.seed(42)

DATA_DIR = Path(__file__).parent
LOGS_DIR = DATA_DIR / "logs"
LOGS_DIR.mkdir(exist_ok=True)

EVENT_TYPES = ["disengagement", "near_miss", "sensor_fault"]
ROAD_TYPES = ["urban_intersection", "highway_merge", "residential", "unprotected_left_turn"]
WEATHER = ["clear", "light_rain", "heavy_rain", "fog", "glare"]

# Each scenario has a hidden ground-truth severity + root cause, used only
# for scoring the agent's output afterward -- the agent never sees these.
SCENARIOS = [
    {
        "event_type": "disengagement",
        "road_type": "unprotected_left_turn",
        "weather": "glare",
        "perception_note": "Oncoming vehicle bounding box flickered (confidence dropped 0.91->0.34) for 400ms during turn.",
        "planner_note": "Planner requested hard brake; safety driver disengaged 0.6s before planner's own correction would have executed.",
        "vehicle_note": "Deceleration 0.3g, no contact, no lane departure.",
        "ground_truth_severity": "moderate",
        "ground_truth_root_cause": "Perception confidence dip under sun glare on oncoming vehicle detection, planner was already correcting.",
    },
    {
        "event_type": "near_miss",
        "road_type": "urban_intersection",
        "weather": "heavy_rain",
        "perception_note": "Pedestrian detected 1.2s later than baseline model performance for wet conditions; lidar return degraded by rain.",
        "planner_note": "Emergency brake triggered at 0.8s to collision, stopped 1.4m from crosswalk.",
        "vehicle_note": "Hard brake, 0.7g deceleration, ABS engaged, no contact.",
        "ground_truth_severity": "severe",
        "ground_truth_root_cause": "Lidar pedestrian detection latency degraded in heavy rain, close call at intersection.",
    },
    {
        "event_type": "sensor_fault",
        "road_type": "highway_merge",
        "weather": "clear",
        "perception_note": "Rear-right camera returned corrupted frames for 2.1s during lane change evaluation.",
        "planner_note": "Planner fell back to radar-only for the affected sector and deferred the lane change by one cycle.",
        "vehicle_note": "No maneuver executed, vehicle held lane, no braking.",
        "ground_truth_severity": "minor",
        "ground_truth_root_cause": "Transient camera frame corruption, redundant radar fallback worked as designed.",
    },
    {
        "event_type": "disengagement",
        "road_type": "residential",
        "weather": "clear",
        "perception_note": "Static object (parked trailer) misclassified as dynamic actor for 1.8s, triggering unnecessary yield prediction.",
        "planner_note": "Planner queued unnecessary yield behind trailer; safety driver disengaged out of caution, no hazard present.",
        "vehicle_note": "Vehicle had already begun slowing but no hazard was present.",
        "ground_truth_severity": "minor",
        "ground_truth_root_cause": "Static/dynamic misclassification of a parked trailer, no actual safety hazard.",
    },
    {
        "event_type": "near_miss",
        "road_type": "highway_merge",
        "weather": "fog",
        "perception_note": "Merging vehicle in adjacent lane detected at reduced range (38m vs typical 90m) due to fog attenuation on radar+camera fusion.",
        "planner_note": "Planner aborted merge with 0.4s margin after detecting closing speed mismatch.",
        "vehicle_note": "Aggressive deceleration 0.5g, no contact, following vehicle had to brake.",
        "ground_truth_severity": "severe",
        "ground_truth_root_cause": "Fog-degraded long-range detection reduced margin on highway merge below design target.",
    },
]


def generate_events(n=5, out_path=None):
    events = []
    base_time = datetime(2026, 8, 24, 7, 0, 0)
    for i in range(n):
        scenario = SCENARIOS[i % len(SCENARIOS)]
        event_id = f"EVT-{uuid.uuid4().hex[:8]}"
        timestamp = (base_time + timedelta(hours=random.randint(0, 96),
                                            minutes=random.randint(0, 59))).isoformat()

        event = {
            "event_id": event_id,
            "timestamp": timestamp,
            "vehicle_id": f"WV-{random.randint(100, 999)}",
            "event_type": scenario["event_type"],
            "road_type": scenario["road_type"],
            "weather": scenario["weather"],
            # ground truth kept separate so the agent's prompt never sees it
            "_ground_truth_severity": scenario["ground_truth_severity"],
            "_ground_truth_root_cause": scenario["ground_truth_root_cause"],
        }
        events.append(event)

        event_log_dir = LOGS_DIR / event_id
        event_log_dir.mkdir(exist_ok=True)

        (event_log_dir / "perception_log.json").write_text(json.dumps({
            "event_id": event_id,
            "note": scenario["perception_note"],
        }, indent=2))

        (event_log_dir / "planner_log.json").write_text(json.dumps({
            "event_id": event_id,
            "note": scenario["planner_note"],
        }, indent=2))

        (event_log_dir / "vehicle_state.json").write_text(json.dumps({
            "event_id": event_id,
            "note": scenario["vehicle_note"],
        }, indent=2))

        (event_log_dir / "weather.json").write_text(json.dumps({
            "event_id": event_id,
            "conditions": scenario["weather"],
            "road_type": scenario["road_type"],
        }, indent=2))

    out_path = out_path or (DATA_DIR / "events.json")
    Path(out_path).write_text(json.dumps(events, indent=2))
    return events


if __name__ == "__main__":
    events = generate_events(n=5)
    print(f"Generated {len(events)} synthetic events -> data/events.json")
    for e in events:
        print(f"  {e['event_id']}  {e['event_type']:15s}  {e['road_type']:24s}  {e['weather']}")
