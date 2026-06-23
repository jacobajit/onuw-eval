from __future__ import annotations

import json
import unittest

from onuw_benchmark.agents import AgentContext
from onuw_benchmark.openrouter import ChatJSONResult, OpenRouterAgent, OpenRouterClient, discussion_schema, night_action_schema, vote_schema
from onuw_benchmark.roles import Role
from onuw_benchmark.schemas import NightAction


class FakeClient:
    def __init__(self, responses: list[dict[str, object] | ChatJSONResult]) -> None:
        self.responses = responses
        self.calls: list[dict[str, object]] = []

    def chat_json_result(self, **kwargs: object) -> ChatJSONResult:
        self.calls.append(kwargs)
        response = self.responses.pop(0)
        if isinstance(response, ChatJSONResult):
            return response
        return ChatJSONResult(
            parsed=response,
            message={"content": json.dumps(response), "reasoning": "visible reasoning summary"},
            finish_reason="stop",
            usage={"prompt_tokens": 1, "completion_tokens": 2},
            raw_response={"choices": [{"message": {"content": json.dumps(response)}}]},
        )


class CapturingClient(OpenRouterClient):
    def __init__(self) -> None:
        super().__init__(api_key="test")
        self.payload: dict[str, object] | None = None

    def _post_json(self, path: str, payload: dict[str, object]) -> dict[str, object]:
        self.payload = payload
        return {
            "choices": [
                {
                    "finish_reason": "stop",
                    "message": {
                        "content": '{"ok": true}',
                        "reasoning": "provider reasoning summary",
                        "reasoning_details": [{"type": "summary", "text": "details"}],
                    },
                }
            ],
            "usage": {"prompt_tokens": 3, "completion_tokens": 4},
        }


class OpenRouterTests(unittest.TestCase):
    def test_client_requests_medium_reasoning_and_extracts_exposed_reasoning(self) -> None:
        client = CapturingClient()
        result = client.chat_json_result(
            model="test/model",
            messages=[{"role": "user", "content": "return json"}],
            schema_name="test",
            schema={"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]},
        )
        self.assertEqual(client.payload["reasoning"], {"effort": "medium", "exclude": False})  # type: ignore[index]
        self.assertTrue(client.payload["include_reasoning"])  # type: ignore[index]
        self.assertEqual(result.reasoning, "provider reasoning summary")
        self.assertEqual(result.reasoning_details, [{"type": "summary", "text": "details"}])

    def test_openrouter_agent_uses_structured_night_action(self) -> None:
        client = FakeClient(
            [
                {
                    "kind": "view_player",
                    "target_player": "B",
                    "target_players": None,
                    "center_card": None,
                    "center_cards": None,
                    "reasoning": "check a neighbor",
                }
            ]
        )
        agent = OpenRouterAgent("A", model="test/model", client=client)  # type: ignore[arg-type]
        context = AgentContext(
            player_id="A",
            players=["A", "B", "C"],
            initial_role=Role.SEER,
            current_role=Role.SEER,
            legal_actions=["view_player", "view_two_center"],
        )
        action = agent.choose_night_action(context)
        self.assertEqual(action, NightAction(kind="view_player", target_player="B", reasoning="check a neighbor"))
        self.assertEqual(client.calls[0]["schema_name"], "night_action")
        self.assertEqual(client.calls[0]["reasoning_effort"], "medium")
        payload = json.loads(client.calls[0]["messages"][1]["content"])  # type: ignore[index]
        self.assertEqual(payload["initial_role"], "Seer")
        self.assertEqual(agent.call_log[0].exposed_reasoning, "visible reasoning summary")
        self.assertEqual(agent.call_log[0].structured_output["reasoning"], "check a neighbor")

    def test_strict_schemas_require_all_fields(self) -> None:
        context = AgentContext(
            player_id="A",
            players=["A", "B", "C"],
            initial_role=Role.SEER,
            current_role=Role.SEER,
            legal_actions=["view_player"],
        )
        self.assertEqual(
            night_action_schema(context)["required"],
            ["kind", "target_player", "target_players", "center_card", "center_cards", "reasoning"],
        )
        self.assertEqual(discussion_schema(context)["required"], ["message", "claim", "accusation", "reasoning_summary"])
        self.assertEqual(vote_schema(context)["required"], ["target_player", "reasoning"])


if __name__ == "__main__":
    unittest.main()
