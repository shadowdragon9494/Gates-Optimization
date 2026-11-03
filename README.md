# Gates-Optimization
Introduction

This project is a pet project by Tyler Lee (https://www.linkedin.com/in/tylerlee96548932/) which utilises his aviation and AI knowledge to create a LLM fronted CP-SAT solver which aims to address airport gate assignment problems. 

Note: This pet project started as a hobby so the it is constantly a work in progress as I add more components and features to it. The Webpage development is done through vibe coding as my java and HTML knowledge is only at surface (enough to understand only), kindly verify before actual deployment. 

Why is the gate assignment a problem?
- Gates in an airport is a physical resource that is always constrained, it is something costly to build and maintain and more importantly can't be trivally expanded. There are lot of intricacies to balance these gates assignment and their usage. The aviation ecosystem is a highly matrix web of complex systems and operations. If unplanned, the constraints and chokepoints shifts around (between airport, airlines, ANSPs) and impact the greater ecosystem (both on departure side and arrival side). 

This project works off commercial or dummy data with appropriate schemas as conceived by me. 

## Purpose
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

Build a low-cost, lightweight web proof of concept that assigns a small set of arriving and departing aircraft to **up to five gates** over a configurable time window. The user can change flight times, aircraft, gate availability, and transfer or baggage assumptions, then compare the resulting gate plan and see why assignments were made or rejected.

The POC demonstrates whether the data model and constraints can support gate balancing. It is a planning demonstrator, not an operational airport dispatch system.

## POC boundary

- One selected airport and no more than five gates.
- A small, configurable flight set for one planning window.
- Import flight schedule or status data through a replaceable source adapter, or use clearly labelled synthetic data when credentials or permissions are not available.
- Store normalized data in a documented schema. Retain field-level source and verification details so users can inspect where a value came from.
- Compare a baseline schedule with one or more what-if scenarios.
- Show the gate plan, constraint violations, unresolved inputs, and an explanation of each assignment.
- Keep a human in control: the result is advisory and must not be represented as an approved live gate plan.

## Data strategy and source verification

The application should separate **the data schema** from **the source that supplies each value**. A provider adapter maps vendor fields into the canonical schema; changing providers must not require changing the optimizer or UI.

Candidate flight-data sources to evaluate (coverage, access, retention, commercial-use terms, and cost must be confirmed before selection):

| Data area | Candidate source | What it may provide | What still needs verification |
| --- | --- | --- | --- |
| Published schedules and flight status | [FlightAware AeroAPI](https://www.flightaware.com/commercial/aeroapi/) | Flight schedules/status and aircraft-type information, subject to plan and endpoint | Airport gate assignment, stand restrictions, passenger connections, baggage handling times, and commercial-use rights for the intended deployment |
| Published schedules and connection data | [OAG Flight Info API](https://www.oag.com/flight-info-api) | Schedule, status, reference, and connections products, subject to contract and selected product | The selected airport's local gate and baggage handling data, and whether required fields are included in the quoted plan |
| Schedules and minimum connecting time data | [Cirium schedules and connections](https://www.cirium.com/data/flight-schedules/schedules-and-connections-data/) | Schedule and minimum connecting time data, subject to product and contract | Local gate compatibility and actual baggage-ready/representation times |
| Aircraft dimensions and servicing characteristics | [Boeing airport planning manuals](https://www.boeing.com/commercial/airports/plan-manuals), [Airbus aircraft characteristics](https://www.aircraft.airbus.com/en/customer-care/fleet-wide-care/airport-operations-and-aircraft-characteristics/aircraft-characteristics), and the [FAA airport design advisory circular](https://www.faa.gov/documentLibrary/media/Advisory_Circular/AC-150-5300-13B-Airport-Design-Chg1-w-errata.pdf) | Reference characteristics useful for aircraft and airport planning | Confirm the relevant aircraft variant and the selected airport's own engineering and stand rules |
| Minimum passenger and baggage connection times | [IATA Station Standard MCT](https://www.iata.org/en/publications/manuals/station-standard-minimum-connecting-time-mct/) | A commercial reference product for published minimum connection times | It is not a substitute for local measured baggage transfer/ready times or ground-handler operating data |
| Gate inventory, compatibility and local operating rules | Selected airport operator, airline operations team, or ground handler (official URL to be recorded for the selected airport) | The authoritative local source for stand/gate attributes and restrictions | No airport has been selected yet; this source and its access terms are a POC prerequisite |
| Actual baggage-ready / bag representation time | Selected airport, airline, or ground handler operational source (official URL or document reference to be recorded) | Local measured or approved values, if the data owner provides them | Not assumed to be generally available in public schedule APIs; otherwise label as an explicit scenario assumption and provide a source link for verification |

Do not silently fill missing values. Every field must be marked as one of:

- `verified`: supplied by a source and checked against its documentation or data owner.
- `provided`: supplied by a source but not independently verified for the POC.
- `assumed`: a user-editable scenario input, with an assumption note.
- `unavailable`: no value available; include a direct `verification_url` or explain that the airport/source is not yet selected.

For each source, keep the provider/product name, document or endpoint name, direct URL, access/licensing note, retrieval timestamp, and any relevant version. Store API credentials outside source code. Do not scrape or redistribute vendor data unless the applicable terms allow it.

## Canonical data schema

The schema is the POC deliverable even where source values are not yet available. Exact vendor field names belong in source adapters and a field-mapping document; they should not leak into the optimizer.

| Entity | Core fields | Required provenance / notes |
| --- | --- | --- |
| `Airport` | `airport_id`, `name`, `timezone`, `source_ref` | Airport identifier and time zone; record the authoritative source. Store times in UTC and display in the airport's local time. |
| `Gate` | `gate_id`, `terminal`, `available_from`, `available_to`, `aircraft_type_allowlist`, `max_wingspan_m`, `contact_stand`, `international_capable`, `transfer_zone`, `source_ref` | Gate/stand details and access restrictions must come from the selected airport or be labelled as POC assumptions. Optional attributes may be unavailable. |
| `AircraftType` | `icao_type`, `iata_type`, `manufacturer`, `model`, `wingspan_m`, `length_m`, `source_ref` | Use a stable type code and units. Record the exact manufacturer or authority document used for dimensions. |
| `Flight` | `flight_id`, `marketing_carrier`, `operating_carrier`, `flight_number`, `origin`, `destination`, `aircraft_type`, `registration`, `scheduled_arrival_utc`, `estimated_arrival_utc`, `scheduled_departure_utc`, `estimated_departure_utc`, `passenger_count` | Flight times and aircraft identifiers should cite the provider field/document. Passenger count is optional and should be unavailable unless a permitted source supplies it. |
| `Turnaround` | `flight_id`, `arrival_to_gate_minutes`, `minimum_turn_minutes`, `departure_pushback_buffer_minutes`, `source_ref` | Separate source values from configurable assumptions. Use this to calculate the gate occupancy interval. |
| `Connection` | `inbound_flight_id`, `outbound_flight_id`, `transfer_zone`, `passenger_transfer_min_minutes`, `bag_transfer_min_minutes`, `bag_ready_after_arrival_minutes`, `source_ref` | Local transfer and baggage handling values are likely to require airport, airline, or handler verification. Do not infer baggage viability from passenger MCT alone. |
| `Scenario` | `scenario_id`, `name`, `planning_window`, `flight_overrides`, `gate_overrides`, `constraint_overrides`, `created_at` | Record changed values, who/what changed them, and whether each override is an assumption. |
| `Assignment` | `scenario_id`, `flight_id`, `gate_id`, `occupancy_start_utc`, `occupancy_end_utc`, `status`, `reason_codes` | Include a human-readable reason for the chosen gate, any rejected alternatives, and unresolved data that affects confidence. |
| `Source` | `source_ref`, `provider`, `product_or_document`, `field_or_endpoint`, `url`, `access_or_license_note`, `retrieved_at`, `version` | Link each populated value to a source record. Use `verification_url` when a value is missing or still needs confirmation. |

Each normalized field should be traceable to a source or assumption. A practical representation is a value plus `source_ref`, `verification_status`, and (when needed) `verification_url`/`assumption_note`. Preserve the raw provider record or a permitted reference to it so mappings can be audited.

## Optimization and backend

Use a small Python service for input validation, source adapters, scenario storage, and gate assignment. For this five-gate POC, begin with a deterministic constraint optimizer (for example, Google OR-Tools CP-SAT) rather than training an ML model. This makes hard restrictions reproducible and lets the UI explain results. Keep the assignment engine behind an interface so an ML-based delay or turn-time estimator can be added later if measured data justifies it.

Initial constraints and objectives:

- A flight occupies at most one gate from its arrival/stand-on time through its departure/pushback buffer.
- A gate cannot serve overlapping flights.
- Aircraft-to-gate compatibility and gate availability are hard constraints when verified.
- Transfer-zone and passenger/baggage time requirements can be hard constraints only when their inputs are verified; otherwise show the scenario assumption and compare outcomes.
- Minimize avoidable gate changes, towing, incompatible assignments, and missed transfer/baggage thresholds using explicit, configurable weights.
- Return `infeasible` with a list of conflicting constraints when no valid plan exists; never conceal a failed or incomplete solve.

Keep the first deployment simple: one Python web service, a lightweight HTML/JavaScript scenario board, and SQLite for the small POC dataset. No GPU, model training pipeline, vector database, or always-on agent service is required. Set and measure a runtime memory budget comfortably below the 15 GB Codespace ceiling; target under 1 GB for the POC process unless measurements show a need to raise it. Make external API calls on demand, cache permitted reference data, and include a synthetic-data mode to avoid recurring vendor charges during development.

## Cheap and bounded agentic workflow

Use agentic features only where they reduce manual source work, and keep them outside the gate feasibility calculation:

1. **Source/field mapper (optional):** drafts mappings from a vendor document or sample response into the canonical schema and flags unmapped fields. A developer or data owner approves the mapping.
2. **Data quality reviewer (rules first):** validates types, units, time zones, missing fields, source links, and stale data; produces a list of items requiring verification.
3. **Scenario explainer (optional):** turns optimizer reason codes into a concise explanation and summarizes trade-offs. It cannot change a hard constraint or assignment without an explicit user action.

Keep AI calls optional, user-triggered, limited to small inputs, and cached where permitted. The core POC must work without an LLM key. Do not send licensed or operationally sensitive data to an AI provider unless the data owner and applicable terms permit it.

## Proof-of-concept acceptance criteria

- A user can load synthetic or permitted source data for one airport and up to five gates.
- The schema and field mapping identify the source/document for every available field and give a direct verification link for unavailable fields.
- A user can edit a scenario input and compare the resulting gate plan with the baseline.
- The backend rejects invalid inputs and reports conflicts or missing data clearly.
- The UI shows assignments, occupancy windows, constraint status, provenance, assumptions, and unresolved verification items.
- The same inputs produce the same gate allocation and explanation codes.
- Runtime memory remains below the 15 GB Codespace cap, with actual usage recorded during the demo.
- No paid data/API account is needed to run the synthetic-data demonstration.

## Recommended Git branches

Use short-lived branches and merge each reviewed vertical slice into `main`. Keep `main` runnable and demoable; avoid maintaining a permanent integration branch.

1. `docs/poc-scope-data-schema` — this README, data dictionary, provenance rules, sample synthetic records, and source/field coverage register. Do this first because it defines the backend and UI contract.
2. `feat/python-api-optimizer` — Python API, schema validation, SQLite persistence, deterministic optimizer, and reason codes using synthetic data.
3. `feat/source-adapters` — provider-neutral adapter interface and one selected commercial schedule/status integration, gated by credentials and terms; keep the synthetic adapter available.
4. `feat/scenario-web-ui` — five-gate board, scenario editor, provenance/missing-data views, and infeasibility explanations.
5. `feat/agentic-source-assist` — optional field-mapping and scenario-explanation helpers after the non-AI flow works; keep all AI features optional.
6. `release/five-gate-poc` — create only when the above slices are integrated and a stable demo needs a release candidate; merge the release back to `main` and tag the demo.

If keeping branch count very small is more important than parallel work, merge steps 3 and 5 into the backend/UI branches as separate commits. Do not create the commercial adapter or agent branch until the source/licensing decision and POC schema are reviewed.

## Initial build order

1. Confirm the airport for the demonstration and identify which gate, schedule, aircraft, and baggage fields can actually be obtained and used.
2. Finalize the source/field coverage register and sample schema records, marking unresolved values `unavailable` or `assumed`.
3. Build the optimizer and UI against synthetic data so the proof of concept remains runnable without paid credentials.
4. Add the lowest-cost suitable commercial source adapter after checking current pricing, coverage, permissions, and required fields with the provider.
5. Add optional agentic helpers only after source fields, deterministic results, and user-visible provenance are working.