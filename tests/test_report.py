from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from onuw_benchmark.report import compact_for_report, render_report, write_report


class ReportTests(unittest.TestCase):
    def test_compacts_encrypted_reasoning_payloads(self) -> None:
        data = {
            "llm_call_log": {
                "P1": [
                    {
                        "exposed_reasoning_details": [
                            {"type": "reasoning.encrypted", "id": "r1", "format": "fmt", "data": "abc123"},
                            {"type": "reasoning.summary", "summary": "visible"},
                        ]
                    }
                ]
            }
        }
        compacted = compact_for_report(data)
        encrypted = compacted["llm_call_log"]["P1"][0]["exposed_reasoning_details"][0]
        self.assertTrue(encrypted["omitted"])
        self.assertEqual(encrypted["bytes"], 6)
        self.assertNotIn("data", encrypted)

    def test_renders_and_writes_report(self) -> None:
        data = {
            "players": ["P1", "P2"],
            "agents": {"P1": {"model": "m1"}, "P2": {"model": "m2"}},
            "initial_roles": {"P1": "Seer", "P2": "Werewolf"},
            "final_roles": {"P1": "Seer", "P2": "Werewolf"},
            "initial_center": ["Villager", "Robber", "Drunk"],
            "final_center": ["Villager", "Robber", "Drunk"],
            "killed": ["P2"],
            "winners": ["P1"],
            "winner_reasons": {"P1": "Village team killed at least one Werewolf"},
            "votes": [{"voter": "P1", "target_player": "P2", "reasoning": "wolf"}],
            "transcript": [{"speaker": "P1", "round_index": 0, "message": "I saw P2.", "claim": "Seer"}],
            "game_log": [{"phase": "resolution", "index": 0, "killed": ["P2"], "winners": ["P1"]}],
            "llm_call_log": {"P1": []},
        }
        html = render_report(data, source_name="sample.json")
        self.assertIn("One Night Ultimate Werewolf Run", html)
        self.assertIn("run-data", html)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "run.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            output = write_report(path)
            self.assertTrue(output.exists())
            self.assertEqual(output.suffix, ".html")


if __name__ == "__main__":
    unittest.main()
