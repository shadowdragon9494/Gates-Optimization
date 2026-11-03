# --- Test dependencies and shared synthetic flight fixture ---
import json
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from types import SimpleNamespace
from unittest.mock import Mock, patch

import gate_solver
import server
from gate_assistant import GateAssistant, TOOLS


def flight(identifier, gate, start, end, model="A321NEO"):
    return {"aircraft_id": identifier, "model": model, "gate": gate,
            "scheduled_landing": start, "scheduled_departure": end,
            "passenger_count": 0}


# --- CP-SAT base-scenario, constraint, and fallback tests ---
class SolverTests(unittest.TestCase):
    def test_reassignment_and_midnight_conflict(self):
        flights = [flight("a", "Gate 11", "2300H", "0100H"),
                   flight("b", "Gate 11", "0030H", "0200H"),
                   flight("c", "Gate 12", "0800H", "0900H"),
                   flight("d", "Gate 1", "2300H", "0100H", "A380-800")]
        with patch.object(gate_solver, "load_flights", return_value=flights):
            result = gate_solver.optimize_gates(time_limit_seconds=2)
        self.assertEqual(result["status"], "OPTIMAL")
        self.assertEqual(result["original_conflicts"], 1)
        self.assertEqual(result["optimized_conflicts"], 0)
        self.assertEqual(result["aircraft_moved"], 1)
        self.assertEqual(result["assignments"][3]["optimized_gate"], "Gate 1")
        self.assertEqual(result["assignments"][0]["duration_minutes"], 120)

    def test_flexible_gates_change_solution(self):
        flights = [flight("a", "Gate 11", "0900H", "1000H"),
                   flight("b", "Gate 11", "0900H", "1000H"),
                   flight("c", "Gate 1", "1200H", "1300H", "A380-800")]
        with patch.object(gate_solver, "load_flights", return_value=flights):
            separate = gate_solver.optimize_gates(gate_count=11, time_limit_seconds=2)
            flexible = gate_solver.optimize_gates(
                flexible_gates=True, gate_count=11, time_limit_seconds=2
            )
        self.assertEqual(separate["optimized_conflicts"], 1)
        self.assertEqual(flexible["optimized_conflicts"], 0)

    def test_validation(self):
        for kwargs in [{"dataset": "../../secret"}, {"flexible_gates": "false"},
                       {"time_limit_seconds": True}, {"time_limit_seconds": 61}]:
            with self.assertRaises(ValueError):
                gate_solver.optimize_gates(**kwargs)
        with self.assertRaises(ValueError):
            gate_solver.minute("2560H")
        for kwargs in [{"aircraft_count": 301}, {"gate_count": 41},
                       {"lock_percentage": 101}, {"wing_to_wing_connections": 1_000_001},
                       {"ground_handling_minutes_per_passenger": 1}]:
            with self.assertRaises(ValueError):
                gate_solver.optimize_gates(**kwargs)

    def test_solver_accepts_sixty_second_limit(self):
        flights = [flight("a", "Gate 11", "0900H", "1000H")]
        solver = Mock()
        solver.parameters = SimpleNamespace()
        solver.Solve.return_value = gate_solver.cp_model.OPTIMAL
        solver.StatusName.return_value = "OPTIMAL"
        solver.Value.return_value = 11
        solver.ObjectiveValue.return_value = 0
        solver.BestObjectiveBound.return_value = 0
        with patch.object(gate_solver, "load_flights", return_value=flights), \
                patch.object(gate_solver.cp_model, "CpSolver", return_value=solver):
            result = gate_solver.optimize_gates(
                aircraft_count=1, lock_percentage=0, time_limit_seconds=60
            )
        self.assertEqual(result["time_limit_seconds"], 60)
        self.assertEqual(result["status"], "OPTIMAL")
        self.assertEqual(solver.parameters.max_time_in_seconds, 60)

    def test_base_scenario_loads_three_hundred_flights_and_passenger_counts(self):
        flights = gate_solver.load_flights("default", 300)
        self.assertEqual(len(flights), 300)
        self.assertTrue(all(isinstance(flight["passenger_count"], int) for flight in flights))
        self.assertEqual(gate_solver.DEFAULT_LOCK_PERCENTAGE, 5)
        candidates = [
            list(range(1, 11)) if flight["model"] == "A380-800"
            else list(range(11, 41))
            for flight in flights
        ]
        original = [int(flight["gate"].split()[1]) for flight in flights]
        locked, target = gate_solver._locked_aircraft(
            flights, candidates, original, gate_solver.DEFAULT_LOCK_PERCENTAGE
        )
        self.assertEqual(target, 15)
        self.assertEqual(len(locked), 15)

    def test_passenger_handling_overrides_and_zero_passenger_fallback(self):
        flights = [flight("a", "Gate 11", "0900H", "1000H"),
                   flight("b", "Gate 11", "1000H", "1100H", "B777-9"),
                   flight("c", "Gate 12", "1100H", "1200H")]
        flights[0]["passenger_count"] = 100
        flights[1]["passenger_count"] = 50
        with patch.object(gate_solver, "load_flights", return_value=flights):
            result = gate_solver.optimize_gates(
                aircraft_count=3,
                lock_percentage=0,
                ground_handling_minutes_per_passenger=3,
                ground_handling_overrides=[{
                    "target_type": "aircraft",
                    "target": "a",
                    "minutes_per_passenger": 2,
                }, {
                    "target_type": "model",
                    "target": "B777-9",
                    "minutes_per_passenger": 4,
                }],
                time_limit_seconds=2,
            )
        durations = {row["aircraft_id"]: row["duration_minutes"] for row in result["assignments"]}
        self.assertEqual(durations, {"a": 200, "b": 200, "c": 120})

    def test_connections_require_close_arrivals_and_adjacent_gates(self):
        flights = [flight("a", "Gate 11", "0900H", "1000H"),
                   flight("b", "Gate 11", "0930H", "1030H")]
        with patch.object(gate_solver, "load_flights", return_value=flights):
            result = gate_solver.optimize_gates(
                gate_count=12,
                aircraft_count=2,
                lock_percentage=0,
                wing_to_wing_connections=1,
                time_limit_seconds=2,
            )
        self.assertEqual(result["connections_fulfilled"], 1)
        first, second = result["connection_pairs"][0]["gates"]
        self.assertEqual(abs(int(first.split()[1]) - int(second.split()[1])), 1)

    def test_unresolved_overlap_reports_connection_or_capacity_reason(self):
        flights = [flight("a", "Gate 11", "0900H", "1000H"),
                   flight("b", "Gate 11", "0930H", "1030H")]
        with patch.object(gate_solver, "load_flights", return_value=flights):
            connection_result = gate_solver.optimize_gates(
                gate_count=11,
                aircraft_count=2,
                lock_percentage=0,
                wing_to_wing_connections=1,
                time_limit_seconds=2,
            )
            capacity_result = gate_solver.optimize_gates(
                gate_count=11,
                aircraft_count=2,
                lock_percentage=0,
                time_limit_seconds=2,
            )
        self.assertEqual(
            connection_result["optimized_conflict_details"][0]["reason"],
            "connection requirement",
        )
        self.assertEqual(
            capacity_result["optimized_conflict_details"][0]["reason"],
            "insufficient compatible gates based on schedule",
        )

    def test_lock_threshold_skips_solver_and_returns_original_plan(self):
        flights = [flight("a", "Gate 11", "0900H", "1000H"),
                   flight("b", "Gate 11", "0930H", "1030H")]
        with patch.object(gate_solver, "load_flights", return_value=flights), \
                patch.object(gate_solver.cp_model.CpSolver, "Solve") as solve:
            result = gate_solver.optimize_gates(
                aircraft_count=2, lock_percentage=81, time_limit_seconds=2
            )
        solve.assert_not_called()
        self.assertEqual(result["status"], "SKIPPED")
        self.assertFalse(result["solver_ran"])
        self.assertEqual(result["locked_aircraft_count"], 2)
        self.assertEqual(result["optimized_conflicts"], result["original_conflicts"])

    def test_no_compatible_gate_is_returned_as_unresolved(self):
        flights = [flight("a", "Gate 11", "0900H", "1000H", "A321NEO")]
        with patch.object(gate_solver, "load_flights", return_value=flights):
            result = gate_solver.optimize_gates(
                gate_count=10, aircraft_count=1, lock_percentage=0
            )
        self.assertEqual(result["status"], "INFEASIBLE")
        self.assertFalse(result["solver_ran"])
        self.assertEqual(
            result["unresolved_aircraft"][0]["reason"],
            "insufficient compatible gates based on schedule",
        )

    def test_eighty_percent_lock_rate_still_runs_and_explains_fixed_gate_conflict(self):
        flights = [flight("a", "Gate 11", "0900H", "1000H"),
                   flight("b", "Gate 11", "0930H", "1030H")]
        with patch.object(gate_solver, "load_flights", return_value=flights):
            result = gate_solver.optimize_gates(
                aircraft_count=2, lock_percentage=80, time_limit_seconds=2
            )
        self.assertTrue(result["solver_ran"])
        self.assertEqual(result["locked_aircraft_count"], 2)
        self.assertEqual(result["optimized_conflict_details"][0]["reason"], "fixed aircraft gate")

    def test_oversized_connection_request_reports_fulfilled_maximum(self):
        flights = [flight("a", "Gate 11", "0900H", "1000H"),
                   flight("b", "Gate 11", "0930H", "1030H")]
        with patch.object(gate_solver, "load_flights", return_value=flights):
            result = gate_solver.optimize_gates(
                gate_count=12,
                aircraft_count=2,
                lock_percentage=0,
                wing_to_wing_connections=151,
                time_limit_seconds=2,
            )
        self.assertEqual(result["connections_fulfilled"], 1)
        self.assertEqual(result["unfulfilled_connection_count"], 150)
        self.assertEqual(result["status"], "OPTIMAL")
        self.assertTrue(result["connection_shortfall_reason"])

    def test_timeout_fallback_is_explicit_and_never_worse_than_original(self):
        flights = [flight("a", "Gate 11", "0900H", "1000H"),
                   flight("b", "Gate 11", "0900H", "1000H"),
                   flight("c", "Gate 12", "1200H", "1300H")]
        with patch.object(gate_solver, "load_flights", return_value=flights), \
                patch.object(gate_solver.cp_model.CpSolver, "Solve", return_value=gate_solver.cp_model.UNKNOWN):
            result = gate_solver.optimize_gates()
        self.assertEqual(result["status"], "HEURISTIC")
        self.assertEqual(result["solver_status"], "UNKNOWN")
        self.assertIsNone(result["objective_bound"])
        self.assertLessEqual(result["optimized_conflicts"], result["original_conflicts"])
        self.assertEqual(len(result["assignments"]), len(flights))


# --- LLM function-call and conversation-state tests ---
class AssistantTests(unittest.TestCase):
    def test_llm_tool_allows_one_minute_solver_limit(self):
        self.assertEqual(
            TOOLS[0]["parameters"]["properties"]["time_limit_seconds"]["maximum"],
            60,
        )

    def test_tool_execution_and_summary_preserve_full_result(self):
        call = SimpleNamespace(type="function_call", name="optimize_gates", call_id="call_1",
                               arguments=json.dumps({"dataset": "default", "flexible_gates": True,
                                                     "time_limit_seconds": 10,
                                                     "aircraft_count": 300, "gate_count": 40,
                                                     "lock_percentage": 5,
                                                     "wing_to_wing_connections": 0,
                                                     "ground_handling_minutes_per_passenger": None,
                                                     "ground_handling_overrides": []}))
        client = Mock()
        client.responses.create.side_effect = [SimpleNamespace(output=[call], output_text=""),
                                              SimpleNamespace(output=[], output_text="Computed plan.")]
        assistant = GateAssistant(client=client)
        result = {"status": "FEASIBLE", "optimized_conflicts": 2, "assignments": [{"aircraft_id": "a"}]}
        with patch("gate_assistant.optimize_gates", return_value=result) as solve:
            self.assertEqual(assistant.ask("Optimise"), "Computed plan.")
        solve.assert_called_once_with(
            dataset="default", flexible_gates=True, time_limit_seconds=10,
            aircraft_count=300, gate_count=40, lock_percentage=5,
            wing_to_wing_connections=0,
            ground_handling_minutes_per_passenger=None,
            ground_handling_overrides=[],
        )
        self.assertEqual(assistant.last_results, [result])
        sent = client.responses.create.call_args.kwargs["input"][-1]
        self.assertEqual(sent["call_id"], "call_1")
        self.assertNotIn("assignments", json.loads(sent["output"]))
        self.assertFalse(client.responses.create.call_args.kwargs["store"])

    def test_failed_turn_does_not_corrupt_history(self):
        client = Mock()
        client.responses.create.side_effect = RuntimeError("Connection lost")
        assistant = GateAssistant(client=client)
        with self.assertRaises(RuntimeError):
            assistant.ask("Optimise")
        self.assertEqual(assistant.history, [])


# --- HTTP endpoint, validation, and response-shape tests ---
class HTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.thread.join()

    def request(self, method, path, data=None, headers=None):
        connection = HTTPConnection(*self.httpd.server_address, timeout=5)
        connection.request(method, path, json.dumps(data) if data is not None else None,
                           headers or {"Content-Type": "application/json"})
        response = connection.getresponse()
        status, body = response.status, response.read()
        connection.close()
        return status, body

    def test_page_and_assets(self):
        for path in ["/", "/planner.js", "/planner.css", "/api/config"]:
            status, body = self.request("GET", path)
            self.assertEqual(status, 200)
            self.assertTrue(body)
        self.assertEqual(self.request("GET", "/../gate_assistant.py")[0], 404)

    def test_solver_endpoint_and_bad_input(self):
        options = {
            "dataset": "default",
            "flexible_gates": False,
            "time_limit_seconds": 10,
            "aircraft_count": 300,
            "gate_count": 40,
            "lock_percentage": 5,
            "wing_to_wing_connections": 0,
            "ground_handling_minutes_per_passenger": None,
            "ground_handling_overrides": [],
        }
        with patch("server.optimize_gates", return_value={"status": "OPTIMAL"}) as solve:
            status, body = self.request("POST", "/api/solve", options)
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["results"][0]["status"], "OPTIMAL")
        solve.assert_called_once_with(**options)
        with patch("server.optimize_gates", return_value={"status": "OPTIMAL"}):
            legacy_status, _ = self.request("POST", "/api/solve", {"dataset": "default"})
        self.assertEqual(legacy_status, 200)
        self.assertEqual(self.request("POST", "/api/solve", {"time_limit_seconds": 999})[0], 400)
        self.assertEqual(self.request("POST", "/api/chat", {"message": ""})[0], 400)
        self.assertEqual(self.request("POST", "/api/solve", {}, {
            "Content-Type": "application/json", "Origin": "https://unrelated.example"})[0], 403)

    def test_missing_key_returns_actionable_error(self):
        with patch.dict("os.environ", {"OPENAI_API_KEY": ""}):
            status, body = self.request("POST", "/api/chat", {"message": "Optimise"})
        self.assertEqual(status, 503)
        self.assertIn("OPENAI_API_KEY", json.loads(body)["error"])

    def test_chat_returns_animation_data_and_reuses_conversation(self):
        assistant = Mock()
        assistant.ask.return_value = "Here is the computed plan."
        assistant.last_results = [{"status": "FEASIBLE", "assignments": [{"aircraft_id": "a"}]}]
        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-placeholder"}), \
                patch("server.GateAssistant", return_value=assistant) as factory:
            status, body = self.request("POST", "/api/chat", {"message": "Optimise"})
            data = json.loads(body)
            self.assertEqual(status, 200)
            self.assertEqual(data["answer"], assistant.ask.return_value)
            self.assertEqual(data["results"], assistant.last_results)
            status, _ = self.request("POST", "/api/chat", {
                "message": "Explain that", "session_id": data["session_id"]})
            self.assertEqual(status, 200)
            factory.assert_called_once()
            self.assertEqual(assistant.ask.call_count, 2)
        server.SESSIONS.pop(data["session_id"])


if __name__ == "__main__":
    unittest.main()
