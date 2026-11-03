"""Reusable CP-SAT model for the airport gate-planning base scenario."""

# --- Imports and base-scenario constants ---
import csv
import math
import random
import re
from pathlib import Path

from ortools.sat.python import cp_model

ROOT = Path(__file__).resolve().parent
DATASETS = {
    name: ROOT / filename
    for name, filename in {
        "default": "dummy_flight_schedule.csv",
        "ideal": "dummy_flight_schedule_ideal.csv",
        "realistic": "dummy_flight_schedule_realistic.csv",
    }.items()
}
PASSENGER_DATA = ROOT / "dummy_passenger_movement.csv"
AIRCRAFT_MODELS = {"A380-800", "B777-9", "A350-1000", "B737 MAX", "A321NEO"}
MINUTES_PER_DAY = 24 * 60
MAX_AIRCRAFT = 300
MAX_GATES = 40
MAX_SOLVER_TIME_SECONDS = 60
MAX_CONNECTION_REQUEST = 1_000_000
DEFAULT_GROUND_HANDLING_MINUTES = 120
MIN_PASSENGER_HANDLING_RATE = 2
MAX_PASSENGER_HANDLING_RATE = 5
# The base-scenario default locks 5% of aircraft at their original gates.
DEFAULT_LOCK_PERCENTAGE = 5
MAX_SOLVER_LOCK_PERCENTAGE = 80
RANDOM_SEED = 17


# --- Schedule parsing and input validation ---
def minute(text):
    """Convert the schedule's HHMMH time format into minutes after midnight."""
    if not isinstance(text, str) or not re.fullmatch(r"(?:[01]\d|2[0-3])[0-5]\dH", text):
        raise ValueError(f"Invalid schedule time: {text!r}; expected HHMMH")
    return int(text[:2]) * 60 + int(text[2:4])


def _validate_integer(value, name, minimum, maximum):
    """Reject booleans and out-of-range values for integer scenario settings."""
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f"{name} must be an integer between {minimum} and {maximum}")


def load_flights(dataset="default", aircraft_count=MAX_AIRCRAFT):
    """Load the selected schedule and join passenger counts by aircraft ID."""
    if not isinstance(dataset, str) or dataset not in DATASETS:
        raise ValueError("dataset must be default, ideal, or realistic")
    _validate_integer(aircraft_count, "aircraft_count", 1, MAX_AIRCRAFT)

    with DATASETS[dataset].open(newline="") as stream:
        schedule = list(csv.DictReader(stream))
    if not schedule:
        raise ValueError("Schedule is empty")
    if len(schedule) < aircraft_count:
        raise ValueError(
            f"Schedule contains {len(schedule)} aircraft; cannot select {aircraft_count}"
        )

    with PASSENGER_DATA.open(newline="") as stream:
        passenger_rows = list(csv.DictReader(stream))
    passenger_counts = {}
    for row in passenger_rows:
        identifier = row.get("aircraft_id")
        if not identifier or identifier in passenger_counts:
            raise ValueError("Passenger data must have present, unique aircraft IDs")
        try:
            passenger_count = int(row["OD"]) + int(row["TT"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"Invalid passenger count for {identifier}") from exc
        if passenger_count < 0:
            raise ValueError(f"Passenger count cannot be negative for {identifier}")
        passenger_counts[identifier] = passenger_count

    selected = schedule[:aircraft_count]
    identifiers = set()
    flights = []
    for source in selected:
        flight = dict(source)
        identifier = flight.get("aircraft_id")
        if not identifier or identifier in identifiers:
            raise ValueError("Aircraft IDs must be present and unique")
        identifiers.add(identifier)
        if identifier not in passenger_counts:
            raise ValueError(f"Passenger data is missing aircraft {identifier}")
        if not re.fullmatch(r"Gate ([1-9]|[1-3]\d|40)", flight.get("gate", "")):
            raise ValueError("Schedule contains an invalid gate")
        if flight.get("model") not in AIRCRAFT_MODELS:
            raise ValueError("Schedule contains an unsupported aircraft model")
        minute(flight.get("scheduled_landing"))
        minute(flight.get("scheduled_departure"))
        flight["passenger_count"] = passenger_counts[identifier]
        flights.append(flight)
    return flights


# --- Ground-handling override validation and duration calculation ---
def _handling_overrides(overrides, flights):
    """Validate per-aircraft and per-model passenger handling-rate overrides."""
    if overrides is None:
        return {}, {}
    if not isinstance(overrides, list):
        raise ValueError("ground_handling_overrides must be a list")

    aircraft_ids = {flight["aircraft_id"] for flight in flights}
    aircraft_rates, model_rates = {}, {}
    for override in overrides:
        if not isinstance(override, dict) or set(override) != {
            "target_type", "target", "minutes_per_passenger"
        }:
            raise ValueError(
                "Each handling override needs target_type, target, and minutes_per_passenger"
            )
        target_type, target = override["target_type"], override["target"]
        if not isinstance(target_type, str) or not isinstance(target, str) or not target.strip():
            raise ValueError("Handling override target_type and target must be non-empty strings")
        rate = override["minutes_per_passenger"]
        _validate_integer(
            rate, "minutes_per_passenger",
            MIN_PASSENGER_HANDLING_RATE, MAX_PASSENGER_HANDLING_RATE,
        )
        if target_type == "aircraft":
            if target not in aircraft_ids:
                raise ValueError(f"Unknown selected aircraft in handling override: {target}")
            rates = aircraft_rates
        elif target_type == "model":
            if target not in AIRCRAFT_MODELS:
                raise ValueError(f"Unsupported aircraft model in handling override: {target}")
            rates = model_rates
        else:
            raise ValueError("handling override target_type must be aircraft or model")
        if target in rates:
            raise ValueError(f"Duplicate handling override for {target}")
        rates[target] = rate
    return aircraft_rates, model_rates


def _ground_handling_minutes(flight, global_rate, aircraft_rates, model_rates):
    """Apply aircraft, model, global, then two-hour fallback handling settings."""
    passenger_count = flight["passenger_count"]
    if passenger_count == 0:
        return DEFAULT_GROUND_HANDLING_MINUTES
    rate = aircraft_rates.get(
        flight["aircraft_id"],
        model_rates.get(flight["model"], global_rate),
    )
    if rate is None:
        return DEFAULT_GROUND_HANDLING_MINUTES
    return passenger_count * rate


# --- Circular occupancy intervals and conflict reporting ---
def _occupied_minutes(start, duration):
    """Return unique occupied minutes for a flight in the repeating daily schedule."""
    return {(start + offset) % MINUTES_PER_DAY for offset in range(min(duration, MINUTES_PER_DAY))}


def _overlap_pairs(occupied):
    """Build per-flight overlap pairs and their daily overlap-minute counts."""
    overlaps = {}
    for first in range(len(occupied)):
        for second in range(first + 1, len(occupied)):
            shared = occupied[first].intersection(occupied[second])
            if shared:
                overlaps[(first, second)] = len(shared)
    return overlaps


def _conflict_details(flights, assignments, overlaps, locked_indices, connection_shortfall):
    """Explain every same-gate overlapping pair in a returned assignment."""
    details = []
    for (first, second), overlap_minutes in overlaps.items():
        if assignments[first] != assignments[second]:
            continue
        if first in locked_indices or second in locked_indices:
            reason = "fixed aircraft gate"
        elif connection_shortfall and (
            (minute(flights[first]["scheduled_landing"])
             - minute(flights[second]["scheduled_landing"])) % MINUTES_PER_DAY <= 60
            or
            (minute(flights[second]["scheduled_landing"])
             - minute(flights[first]["scheduled_landing"])) % MINUTES_PER_DAY <= 60
        ):
            reason = "connection requirement"
        else:
            reason = "insufficient compatible gates based on schedule"
        details.append({
            "gate": assignments[first],
            "aircraft_ids": [flights[first]["aircraft_id"], flights[second]["aircraft_id"]],
            "overlap_minutes": overlap_minutes,
            "reason": reason,
        })
    return details


# --- Random lock and connection candidate selection ---
def _locked_aircraft(flights, candidates, original, lock_percentage):
    """Choose a repeatable random sample of aircraft whose original gates can be locked."""
    target = math.floor(len(flights) * lock_percentage / 100 + 0.5)
    eligible = [
        index for index, choices in enumerate(candidates)
        if original[index] in choices
    ]
    generator = random.Random(RANDOM_SEED)
    selected = generator.sample(eligible, min(target, len(eligible)))
    return set(selected), target


def _connection_candidates(flights, candidates):
    """Return close-arrival pairs that can physically occupy consecutive gates."""
    eligible = []
    for first in range(len(flights)):
        first_arrival = minute(flights[first]["scheduled_landing"])
        for second in range(first + 1, len(flights)):
            second_arrival = minute(flights[second]["scheduled_landing"])
            gap = min(
                (first_arrival - second_arrival) % MINUTES_PER_DAY,
                (second_arrival - first_arrival) % MINUTES_PER_DAY,
            )
            if gap > 60:
                continue
            if any(
                abs(first_gate - second_gate) == 1
                for first_gate in candidates[first]
                for second_gate in candidates[second]
            ):
                eligible.append((first, second))
    random.Random(RANDOM_SEED).shuffle(eligible)
    return eligible


def _assignment_connections(flights, assignments, requested):
    """Report a deterministic set of fulfilled, disjoint close-arrival connections."""
    candidates = _connection_candidates(
        flights, [[int(gate.split()[1]) for gate in {assignments[i]}]
                  for i in range(len(flights))]
    )
    # A connection requires consecutive gates, so same-gate aircraft are not connected.
    result, used = [], set()
    for first, second in candidates:
        if len(result) >= requested:
            break
        if first in used or second in used:
            continue
        first_gate = int(assignments[first].split()[1])
        second_gate = int(assignments[second].split()[1])
        if abs(first_gate - second_gate) != 1:
            continue
        used.update((first, second))
        result.append({
            "aircraft_ids": [flights[first]["aircraft_id"], flights[second]["aircraft_id"]],
            "gates": [assignments[first], assignments[second]],
        })
    return result


# --- Public solver entry point and scenario validation ---
def optimize_gates(
    dataset="default",
    flexible_gates=False,
    time_limit_seconds=10,
    aircraft_count=MAX_AIRCRAFT,
    gate_count=MAX_GATES,
    lock_percentage=DEFAULT_LOCK_PERCENTAGE,
    wing_to_wing_connections=0,
    ground_handling_minutes_per_passenger=None,
    ground_handling_overrides=None,
):
    """Minimize conflicts first, then maximize connections, then minimize gate moves."""
    if type(flexible_gates) is not bool:
        raise ValueError("flexible_gates must be a boolean")
    _validate_integer(
        time_limit_seconds, "time_limit_seconds", 1, MAX_SOLVER_TIME_SECONDS
    )
    _validate_integer(aircraft_count, "aircraft_count", 1, MAX_AIRCRAFT)
    _validate_integer(gate_count, "gate_count", 1, MAX_GATES)
    _validate_integer(lock_percentage, "lock_percentage", 0, 100)
    _validate_integer(
        wing_to_wing_connections,
        "wing_to_wing_connections",
        0,
        MAX_CONNECTION_REQUEST,
    )
    if ground_handling_minutes_per_passenger is not None:
        _validate_integer(
            ground_handling_minutes_per_passenger,
            "ground_handling_minutes_per_passenger",
            MIN_PASSENGER_HANDLING_RATE,
            MAX_PASSENGER_HANDLING_RATE,
        )

    flights = load_flights(dataset, aircraft_count)
    aircraft_rates, model_rates = _handling_overrides(ground_handling_overrides, flights)
    gates = [f"Gate {number}" for number in range(1, gate_count + 1)]
    gate_numbers = {gate: int(gate.split()[1]) for gate in gates}

    # --- Build each flight's fixed-arrival occupancy and compatible gate domain ---
    starts, durations, occupied, candidates, original = [], [], [], [], []
    for flight in flights:
        start = minute(flight["scheduled_landing"])
        duration = _ground_handling_minutes(
            flight, ground_handling_minutes_per_passenger, aircraft_rates, model_rates
        )
        a380 = flight["model"] == "A380-800"
        choices = [
            gate_numbers[gate] for gate in gates
            if (gate_numbers[gate] <= 10 if a380 else
                flexible_gates or gate_numbers[gate] > 10)
        ]
        starts.append(start)
        durations.append(duration)
        occupied.append(_occupied_minutes(start, duration))
        candidates.append(choices)
        original.append(flight["gate"])

    # --- Select fixed-gate aircraft and enforce the high-lock solver cutoff ---
    original_gate_numbers = [
        int(flight["gate"].split()[1]) for flight in flights
    ]
    locked_indices, target_lock_count = _locked_aircraft(
        flights, candidates, original_gate_numbers, lock_percentage
    )
    result_base = {
        "dataset": dataset,
        "flexible_gates": flexible_gates,
        "aircraft_count": len(flights),
        "gate_count": gate_count,
        "lock_percentage": lock_percentage,
        "locked_aircraft_count": len(locked_indices),
        "target_locked_aircraft_count": target_lock_count,
        "wing_to_wing_connections_requested": wing_to_wing_connections,
        "ground_handling_default_minutes": DEFAULT_GROUND_HANDLING_MINUTES,
        "time_limit_seconds": time_limit_seconds,
    }

    # --- Preserve the baseline view when a configuration has no compatible gates ---
    invalid_domains = [
        index for index, choices in enumerate(candidates) if not choices
    ]
    if invalid_domains and lock_percentage <= MAX_SOLVER_LOCK_PERCENTAGE:
        original_overlaps = _overlap_pairs(occupied)
        original_conflict_details = _conflict_details(
            flights, original, original_overlaps, locked_indices, False
        )
        assignments = [{
            "aircraft_id": flight["aircraft_id"],
            "model": flight["model"],
            "original_gate": flight["gate"],
            "optimized_gate": flight["gate"],
            "arrival_minute": starts[index],
            "departure_minute": (starts[index] + durations[index]) % MINUTES_PER_DAY,
            "duration_minutes": durations[index],
            "ground_handling_minutes": durations[index],
            "passenger_count": flight["passenger_count"],
            "gate_locked": index in locked_indices,
        } for index, flight in enumerate(flights)]
        unavailable = [{
            "aircraft_id": flights[index]["aircraft_id"],
            "reason": "insufficient compatible gates based on schedule",
        } for index in invalid_domains]
        return {
            **result_base,
            "status": "INFEASIBLE",
            "solver_ran": False,
            "message": "No compatible gate is available for one or more aircraft under this gate-count and gate-policy combination.",
            "original_conflicts": len(original_conflict_details),
            "optimized_conflicts": len(original_conflict_details),
            "aircraft_moved": 0,
            "unresolved_aircraft": unavailable,
            "original_conflict_details": original_conflict_details,
            "optimized_conflict_details": original_conflict_details,
            "connections_fulfilled": 0,
            "unfulfilled_connection_count": wing_to_wing_connections,
            "connection_shortfall_reason": (
                "The selected gate policy leaves no compatible gate for part of the fleet."
                if wing_to_wing_connections else None
            ),
            "connection_pairs": [],
            "unfulfilled_connection_details": [],
            "assignments": assignments,
        }

    # --- Return the original plan without CP-SAT when locks exceed the allowed threshold ---
    if lock_percentage > MAX_SOLVER_LOCK_PERCENTAGE:
        original_overlaps = _overlap_pairs(occupied)
        original_conflict_details = _conflict_details(
            flights, original, original_overlaps, locked_indices, False
        )
        assignments = [{
            "aircraft_id": flight["aircraft_id"],
            "model": flight["model"],
            "original_gate": flight["gate"],
            "optimized_gate": flight["gate"],
            "arrival_minute": starts[index],
            "departure_minute": (starts[index] + durations[index]) % MINUTES_PER_DAY,
            "duration_minutes": durations[index],
            "ground_handling_minutes": durations[index],
            "passenger_count": flight["passenger_count"],
            "gate_locked": index in locked_indices,
        } for index, flight in enumerate(flights)]
        return {
            **result_base,
            "status": "SKIPPED",
            "solver_ran": False,
            "message": (
                "CP-SAT was not run: more than 80% of aircraft are gate-locked. "
                "This is treated as an unconstrained baseline; showing original assignments only."
            ),
            "original_conflicts": len(original_conflict_details),
            "optimized_conflicts": len(original_conflict_details),
            "aircraft_moved": 0,
            "original_conflict_details": original_conflict_details,
            "optimized_conflict_details": original_conflict_details,
            "connections_fulfilled": 0,
            "unfulfilled_connection_count": wing_to_wing_connections,
            "connection_shortfall_reason": (
                "CP-SAT was skipped, so no connection assignments were evaluated."
                if wing_to_wing_connections else None
            ),
            "connection_pairs": [],
            "unfulfilled_connection_details": [],
            "assignments": assignments,
        }

    # --- Apply valid locks as singleton gate domains and generate scenario pairs ---
    for index in locked_indices:
        candidates[index] = [original_gate_numbers[index]]
    overlaps = _overlap_pairs(occupied)
    original_conflict_details = _conflict_details(
        flights, original, overlaps, locked_indices, False
    )
    connection_candidates = (
        _connection_candidates(flights, candidates)
        if wing_to_wing_connections else []
    )
    original_by_index = [
        int(flight["gate"].split()[1]) for flight in flights
    ]

    # --- Create the CP-SAT gate, overlap, connection, and movement variables ---
    model = cp_model.CpModel()
    choices = [
        model.NewIntVarFromDomain(cp_model.Domain.FromValues(domain), f"gate_{index}")
        for index, domain in enumerate(candidates)
    ]
    conflict_vars, move_vars, connection_vars = [], [], []
    conflict_pairs = [
        pair for pair in overlaps
        if set(candidates[pair[0]]).intersection(candidates[pair[1]])
    ]
    for first, second in conflict_pairs:
        conflict = model.NewBoolVar(f"conflict_{first}_{second}")
        model.Add(choices[first] == choices[second]).OnlyEnforceIf(conflict)
        model.Add(choices[first] != choices[second]).OnlyEnforceIf(conflict.Not())
        conflict_vars.append(conflict)

    for index, choice in enumerate(choices):
        moved = model.NewBoolVar(f"moved_{index}")
        model.Add(choice != original_by_index[index]).OnlyEnforceIf(moved)
        model.Add(choice == original_by_index[index]).OnlyEnforceIf(moved.Not())
        move_vars.append(moved)

    for first, second in connection_candidates:
        connected = model.NewBoolVar(f"connection_{first}_{second}")
        forward = model.NewBoolVar(f"connection_forward_{first}_{second}")
        backward = model.NewBoolVar(f"connection_backward_{first}_{second}")
        model.Add(forward + backward == connected)
        model.Add(choices[first] == choices[second] + 1).OnlyEnforceIf(forward)
        model.Add(choices[second] == choices[first] + 1).OnlyEnforceIf(backward)
        connection_vars.append((first, second, connected))

    # --- Limit connection pairing and prioritize conflicts, connections, then moves ---
    for index in range(len(flights)):
        incident = [
            variable for first, second, variable in connection_vars
            if index == first or index == second
        ]
        if incident:
            model.Add(sum(incident) <= 1)
    if connection_vars:
        model.Add(sum(variable for _, _, variable in connection_vars)
                  <= min(wing_to_wing_connections, len(flights) // 2))

    max_connections = min(wing_to_wing_connections, len(flights) // 2)
    move_weight = 1
    connection_weight = len(flights) + 1
    conflict_weight = max_connections * connection_weight + len(flights) + 1
    model.Minimize(
        conflict_weight * sum(conflict_vars)
        - connection_weight * sum(variable for _, _, variable in connection_vars)
        + move_weight * sum(move_vars)
    )

    # --- Add a compatible greedy hint to help CP-SAT find an early incumbent ---
    hint = {}
    for index in sorted(range(len(flights)), key=lambda item: starts[item]):
        choices_for_flight = candidates[index]
        hint[index] = min(
            choices_for_flight,
            key=lambda gate: (
                sum(
                    1 for previous in hint
                    if hint[previous] == gate
                    and occupied[index].intersection(occupied[previous])
                ),
                gate != original_by_index[index],
                gate,
            ),
        )
        model.AddHint(choices[index], hint[index])
    for index, moved in enumerate(move_vars):
        model.AddHint(moved, int(hint[index] != original_by_index[index]))
    for (first, second), conflict in zip(conflict_pairs, conflict_vars):
        model.AddHint(conflict, int(hint[first] == hint[second]))

    # --- Configure and run the bounded CP-SAT search ---
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit_seconds
    solver.parameters.num_search_workers = 2
    solver.parameters.random_seed = RANDOM_SEED
    status = solver.Solve(model)
    status_name = solver.StatusName(status)

    # --- Use solver assignments or an explicitly labelled compatible fallback ---
    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        assigned_numbers = [solver.Value(choice) for choice in choices]
        solver_ran = True
        message = None
        objective = solver.ObjectiveValue()
        objective_bound = solver.BestObjectiveBound()
        connection_pairs = [
            (first, second)
            for first, second, variable in connection_vars
            if solver.Value(variable)
        ]
    elif status == cp_model.UNKNOWN:
        assigned_numbers = [hint[index] for index in range(len(flights))]
        solver_ran = True
        message = (
            "CP-SAT found no incumbent within the limit; showing a compatible "
            "greedy assignment, not a CP-SAT solution."
        )
        objective = None
        objective_bound = None
        connection_pairs = []
    else:
        return {
            **result_base,
            "status": status_name,
            "solver_ran": True,
            "message": "CP-SAT could not produce a gate assignment.",
            "original_conflicts": len(original_conflict_details),
            "optimized_conflicts": None,
            "original_conflict_details": original_conflict_details,
            "optimized_conflict_details": [],
            "assignments": None,
        }

    # --- Calculate before/after conflicts and publish complete browser assignments ---
    assigned = [f"Gate {number}" for number in assigned_numbers]
    optimized_conflict_details = _conflict_details(
        flights,
        assigned,
        overlaps,
        locked_indices,
        wing_to_wing_connections > len(connection_pairs),
    )
    if not connection_pairs and status == cp_model.UNKNOWN:
        fulfilled_connections = _assignment_connections(
            flights, assigned, wing_to_wing_connections
        )
    else:
        fulfilled_connections = [{
            "aircraft_ids": [flights[first]["aircraft_id"], flights[second]["aircraft_id"]],
            "gates": [assigned[first], assigned[second]],
        } for first, second in connection_pairs]
    connected_aircraft = {
        identifier for pair in fulfilled_connections for identifier in pair["aircraft_ids"]
    }
    fulfilled_id_pairs = {
        tuple(pair["aircraft_ids"]) for pair in fulfilled_connections
    }
    unfulfilled_count = max(0, wing_to_wing_connections - len(fulfilled_connections))
    unfulfilled_connections, used_connection_aircraft = [], set(connected_aircraft)
    for first, second in connection_candidates:
        if len(unfulfilled_connections) >= unfulfilled_count:
            break
        pair_ids = (flights[first]["aircraft_id"], flights[second]["aircraft_id"])
        if pair_ids in fulfilled_id_pairs:
            continue
        if pair_ids[0] in used_connection_aircraft or pair_ids[1] in used_connection_aircraft:
            continue
        unfulfilled_connections.append({
            "aircraft_ids": list(pair_ids),
            "original_gates": [flights[first]["gate"], flights[second]["gate"]],
            "gates": [assigned[first], assigned[second]],
            "reason": "connection requirement",
        })
        used_connection_aircraft.update(pair_ids)
    connection_shortfall_reason = None
    if unfulfilled_count and len(unfulfilled_connections) < unfulfilled_count:
        connection_shortfall_reason = (
            "The requested connection count could not be met while honoring gate compatibility, locks, and conflict priority."
        )
    assignments = [{
        "aircraft_id": flight["aircraft_id"],
        "model": flight["model"],
        "original_gate": flight["gate"],
        "optimized_gate": assigned[index],
        "arrival_minute": starts[index],
        "departure_minute": (starts[index] + durations[index]) % MINUTES_PER_DAY,
        "duration_minutes": durations[index],
        "passenger_count": flight["passenger_count"],
        "ground_handling_minutes": durations[index],
        "gate_locked": index in locked_indices,
        "wing_to_wing_connected": flight["aircraft_id"] in connected_aircraft,
    } for index, flight in enumerate(flights)]

    # --- Return solver status, metrics, and conflict reasons for every view ---
    return {
        **result_base,
        "status": "HEURISTIC" if status == cp_model.UNKNOWN else status_name,
        "solver_status": status_name,
        "solver_ran": solver_ran,
        "message": message,
        "original_conflicts": len(original_conflict_details),
        "optimized_conflicts": len(optimized_conflict_details),
        "aircraft_moved": sum(
            original_by_index[index] != assigned_numbers[index]
            for index in range(len(flights))
        ),
        "connections_fulfilled": len(fulfilled_connections),
        "connection_pairs": fulfilled_connections,
        "unfulfilled_connection_count": unfulfilled_count,
        "connection_shortfall_reason": connection_shortfall_reason,
        "unfulfilled_connection_details": unfulfilled_connections,
        "objective": objective,
        "objective_bound": objective_bound,
        "original_conflict_details": original_conflict_details,
        "optimized_conflict_details": optimized_conflict_details,
        "assignments": assignments,
    }
