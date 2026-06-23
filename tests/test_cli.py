from __future__ import annotations

import contextlib
import io
import json
import unittest

from onuw_benchmark.cli import main, summarize_runs


class CliTests(unittest.TestCase):
    def test_summarize_runs_aggregates_player_and_model_rates(self) -> None:
        runs = [
            {
                "players": ["P1", "P2"],
                "winners": ["P1"],
                "killed": ["P2"],
                "agents": {"P1": {"model": "model-a"}, "P2": {"model": "model-b"}},
            },
            {
                "players": ["P1", "P2"],
                "winners": ["P2"],
                "killed": [],
                "agents": {"P1": {"model": "model-a"}, "P2": {"model": "model-b"}},
            },
        ]

        summary = summarize_runs(runs, players=["P1", "P2"])

        self.assertEqual(summary["runs"], 2)
        self.assertEqual(summary["players"]["P1"]["wins"], 1)
        self.assertEqual(summary["players"]["P1"]["games"], 2)
        self.assertEqual(summary["players"]["P1"]["win_rate"], 0.5)
        self.assertEqual(summary["models"]["model-b"]["wins"], 1)
        self.assertEqual(summary["models"]["model-b"]["killed"], 1)
        self.assertEqual(summary["models"]["model-b"]["killed_rate"], 0.5)

    def test_run_json_supports_multiple_runs(self) -> None:
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            exit_code = main(["run", "--runs", "3", "--seed", "10", "--discussion-rounds", "0", "--json"])

        self.assertEqual(exit_code, 0)
        data = json.loads(stdout.getvalue())
        self.assertEqual(data["type"], "multi_run")
        self.assertEqual(data["run_count"], 3)
        self.assertEqual(len(data["runs"]), 3)
        self.assertEqual([run["seed"] for run in data["runs"]], [10, 11, 12])
        self.assertIn("mock", data["summary"]["models"])
        self.assertEqual(data["summary"]["models"]["mock"]["games"], 12)


if __name__ == "__main__":
    unittest.main()
