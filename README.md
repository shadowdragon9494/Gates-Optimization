# Gates-Optimization
[![test](https://github.com/shadowdragon9494/Gates-Optimization/actions/workflows/tests.yml/badge.svg)](https://github.com/shadowdragon9494/Gates-Optimization/actions/workflows/test.yml)
## Introduction

This is a pet project by Tyler Lee (https://www.linkedin.com/in/tylerlee96548932/) which utilizes his aviation and AI knowledge to create a LLM fronted CP-SAT solver which aims to address airport gate assignment problems. I am a Technical Program Manager for emerging technologies in Aviation, Space and AI Programs. Bringing technologies from discovery to deployment and translating the products to real world impact.

Note: This pet project started as a hobby so the it is constantly a work in progress as I add more components and features to it. Vibe coding notice! The Webpage development is done through vibe coding as my java and HTML knowledge is only at surface (enough to understand only), kindly verify before actual deployment. A part of the python code consists of some data science. This was done by me to ensure that the dummy data I have created is robust enough and that it mirrors real world constraint. Some numbers were artificially altered to ensure that the problem exists, please exercise discretion. 

## Context

Aviation is never short of problems. The good innovation and safety record that we have is never by chance. Being a long term strategist in aviation, there are many problems that I want to solve. With the advent of technologies, I have come to realize I could prototype some of them myself and this motivated me to create the first digital product that I have built on top of other things like drones, gliders, 3D printed turbines, robotics etc. Having worked in one of the best airports in the world, we are always asking ourselves how can things be better. There are many issues/questions that we can address but we need to be grounded in reality and not try to solve a problem so big that it would take decades. With projects like these, I aim to create a simple POC to try to articulate aviation problems. AI uptake in aviation is slow and I attribute it to two things (not knowing enough about aviation - a highly matrixed, webbed, complex and most regulated industry) and (the bar to safety is high). So, in my projects, I hope to spur interest for individuals about AI for aviation (we are no strangers to ML but it's time for aviation to try to embrace AI).

## Purpose
Why is the gate assignment a problem?
- Gates in an airport is a physical resource that is always constrained, it is something costly to build and maintain and more importantly can't be trivally expanded. There are lot of intricacies to balance these gates assignment and their usage. The aviation ecosystem is a highly matrix web of complex systems and operations. If unplanned, the constraints and chokepoints shifts around (between airport, airlines, ANSPs) and impact the greater ecosystem (both on departure side and arrival side). 

This project works off commercial or dummy data with appropriate schemas as conceived by me. 

## Constraints, Scenarios, Assumptions and Models

The key thing about addressing an aviation use case is to establish the right correlations between variables. We need to establish a few params that are contributory to the analysis.

### Assumptions 
Broad assumptions were made and the problem was contextualized to be focused on airport instead of the broader eco-system. The problem considers the following as definitions (not quite how ICAO would define) arrival timing in this case is defined as aircraft's time of arrival to the gate. Assumes no taxi timing from runway to gate. We also assume no delays from aircraft arrival and that every arrival reaches at the time that they are intended to. Departure also assumes the same. Airspace and ground handling constraints are not part of this evaluation. Terminal Efficiency, Airside Efficiency and Facilities Utilization rates are all not considered in this example, though in real life there are a lot more correlations between these metrics. We also do not consider finer metrics and differences in things like 'in-block time' and 'off-block time' or even terminal congestion metrics. 

The experimentation here is airlines agnostic and not mapped after any airport.

### Constraints and Data Correlations
There would be a base scenario that we will have as a default and params will be made available for the LLM to input. 

As a baseline we have 300 aircraft on schedule using 40 gates across 24 hours. Each aircraft has a random number of passengers onboard that is mixed between departure/arrival and transit passengers. Proxies are used for aircraft capacities and we only have 5 aircraft types in the simulation (1 aircraft type for Code F gates as per ICAO definition and 4 aircraft types of varying capacities). 

1. Aircraft Type
   - It affects aircraft gate assignment between Code F gates and other gates.
   - Aircraft type has an impact on the ground handling time. In the base scenario we set as 2 hours flat.
    
2. Operational Constraint
   - The simulated aerodrome assumes all arriving aircraft must and will depart after the ground handling time has elapsed. 
   - Base scenario would assume the preceding statement but it will be kept as a variable for the LLM to fill.
   - Estimated Landing Time is assumed to be fixed in all scenarios. So the only moving part is gate assignments.
   
3. Rigid vs Flexible Gates 
   - Original vs Optimised Scenario. In original, every aircraft needs to use their assigned gates. In optimised, the CP-SAT solver is use to shift gate assignments. 
  
4. Passengers and Commercial Complication
   - Wing to Wing connections are not considered in base scenario, assumed to be zero. LLM will allow this to be a variable.
   - Certain aircraft at random will be assigned a lock at random, those aircraft will definitely use those gates.

(Stretched scenario)
* To consider aircraft groups where they need to be assigned in close proximity to facilitate transfers.

### Models 
CP-SAT by Google is one of the famous and promising open source models that is capable of modelling physics and mathematical constraints. The original intention was to do a CNN to correlate the parameters but the code run times were very long so I decided against it at this point. Especially with an LLM frontage, each permutation could take up to 10 minutes of compute time (based on my own home PC set-up). Barring more powerful processing capability, as part of future work, I would love to build a PINNs. 

## Run the planning website

Requires Python 3.10 or later. The HTTP backend serves the website and runs both
OpenAI function calls and CP-SAT. The existing Java server serves only the older
case study and does not provide these API endpoints.

```bash
python -m pip install -r requirements.txt
python server.py --prompt-key
```

Open **http://127.0.0.1:8080/**. You can also launch with `python "LLM API.py"`.
Enter your API key at the hidden terminal prompt each time you start the server.
It stays in the running Python process and is not saved in source code, files,
or your shell history. Press Enter without a key for solver preview only.
`--prompt-key` always prompts; without it, an existing `OPENAI_API_KEY` environment
variable is reused, or a terminal prompt appears if no key is configured.
Keep the API key on the server; do not put it in browser JavaScript or commit it.
The server reads environment variables directly; it does not load `.env` files.
The default model is `gpt-6-luna`; optionally set `OPENAI_MODEL` to another model
available to your OpenAI API project.

Try: “Compare separate and flexible gate policies on the realistic schedule.”
The assistant calls the solver, explains its metrics, and sends the full plan to
the animated gate map. Compare the **Before CP-SAT** original schedule with the
**After CP-SAT** reassignment, then press Play or scrub the clock. Hover over a
gate to see any unresolved conflict and its reason. Download JSON to retain the
assignments and metrics. A direct **Run solver preview** button works without an
OpenAI key and exposes the base-scenario counts, global handling rate, locks, and
connection count. Aircraft/model-specific handling overrides are available in chat.

## How it works

<img width="1672" height="941" alt="image" src="https://github.com/user-attachments/assets/6b18ef23-d344-4c61-aef7-e41771006661" />

Browser → Python HTTP server → OpenAI Responses API → `optimize_gates` → CP-SAT
→ OpenAI explanation plus an assignment-driven browser animation.

`gate_solver.py` extracts the notebook's conflict-first objective into a callable
function. The bundled schedules are allowlisted: `default`, `ideal`, and
`realistic`. The default base scenario selects up to 300 aircraft and up to 40
gates; a lower aircraft count selects the first N rows and a lower gate count
uses Gates 1 through N. Gates 1–10 are A380-compatible; gates 11–40 serve other
aircraft unless the flexible-gates policy is selected. A separate-gate scenario
with too few gates to serve a fleet type is returned as unresolved, not silently
assigned an incompatible gate. Arrivals stay fixed. By default, each
aircraft occupies its gate for 120 minutes, so the calculated departure is its
arrival plus two hours; the source schedule's departure time does not change this
base-scenario handling duration.

The LLM and direct preview can set aircraft count (1–300), gate count (1–40),
wing-to-wing connection count (default 0), and gate-lock percentage (default 5%).
Locks fix randomly selected aircraft at their original gates. A request above
80% locked aircraft returns the original schedule without running CP-SAT.
Passenger counts are OD + TT from `dummy_passenger_movement.csv`. A global,
aircraft-model, or aircraft-specific handling rate can be set from 2–5 minutes
per passenger; aircraft-specific rates take precedence over model rates, which
take precedence over the global rate. The default 120-minute handling time is
used when no rate is provided or an aircraft has zero passengers.

Wing-to-wing pairs are selected from aircraft whose arrival times are within one
hour of each other and must use consecutive gate numbers. Requests can exceed the
number of possible pairs; the result reports requested and fulfilled counts, and
only `OPTIMAL` proves the best fulfilled count under the modeled constraints.
The weighted objective prioritizes zero overlapping same-gate aircraft pairs,
then fulfilled connections, then fewer gate moves. Remaining overlaps are soft unresolved
conflicts. Their hover details identify a fixed aircraft gate, a connection
requirement, or insufficient compatible gates based on the schedule.

The schedule wraps across midnight. A handling duration of at least 24 hours
occupies the gate throughout the repeating daily schedule. The solver search
limit is 1–60 seconds (10 seconds by default); model construction adds processing
time. `FEASIBLE` is an incumbent, not proven optimal; only `OPTIMAL` proves the
weighted objective. `HEURISTIC` means the search timed out without an incumbent
and shows a compatible greedy assignment, not a CP-SAT solution. `SKIPPED` means
the lock threshold prevented a solver run. The map shows occupancy at the current
minute; conflict counts cover overlapping flight pairs across the full day.
Aircraft icons are schematic, not simulated flight paths. Transfer itineraries,
baggage times, delays, gate closures, and custom schedule uploads are not modeled.
The notebook remains the source of the base-scenario assumptions.

Only aggregate solver metrics are passed back to OpenAI; full assignments are
returned directly to the browser. Conversations live in server memory for up to
one hour and disappear on restart. No persistent database is used.

## HTTP endpoints and checks

- `GET /api/config`: whether chat is configured (never exposes the key).
- `POST /api/chat`: `{"message":"Optimise the default schedule","session_id":null}`.
  Returns `session_id`, `answer`, and `results`; reuse the ID for follow-ups.
- `POST /api/solve`: accepts `dataset`, `flexible_gates`, `time_limit_seconds`,
  `aircraft_count`, `gate_count`, `lock_percentage`, `wing_to_wing_connections`,
  `ground_handling_minutes_per_passenger`, and `ground_handling_overrides`.
  `time_limit_seconds` accepts 1–60 seconds; the webpage displays an indeterminate
  progress bar while a planning request is running.
  The override array contains `{ "target_type": "aircraft" | "model",
  "target": "aircraft ID or model", "minutes_per_passenger": 2..5 }` items.
  Returns `results` without calling OpenAI.

```bash
python -m unittest discover -s tests -v
node --check web/planner.js
```

This is a local HTTP prototype, bound to loopback by default. Public hosting needs
a Python/container runtime for OR-Tools, HTTPS, authentication, rate limits and a
job queue for solver work. Sites' Worker runtime cannot execute this Python
CP-SAT backend; deploying just the static files there would not provide a working
solver. No hosted deployment is configured. For local network testing use
`python server.py --host 0.0.0.0 --port 8080` on a trusted network.

OpenAI integration follows the official
[function calling guide](https://developers.openai.com/api/docs/guides/function-calling).

## Future work
- LLM evaluations, prompt caching and building a vectorDB for past queries to reduce token consumptions.
- Alternative solvers like Neural networks or PINNs.


