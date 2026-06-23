from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any
from urllib import error, parse, request

from onuw_benchmark.agents import AgentContext, Observation, PlayerAgent
from onuw_benchmark.roles import Role
from onuw_benchmark.schemas import DiscussionMessage, NightAction, Vote, validate_action_for_role


OPENROUTER_API_URL = "https://openrouter.ai/api/v1"
DEFAULT_MAX_TOKENS = 16000
DEFAULT_REASONING_EFFORT = "medium"
DEFAULT_DISCUSSION_MESSAGE_MAX_CHARS = 2000
DEFAULT_REASONING_SUMMARY_MAX_CHARS = 4000


class OpenRouterError(RuntimeError):
    pass


@dataclass(frozen=True)
class ChatJSONResult:
    parsed: dict[str, Any]
    message: dict[str, Any]
    finish_reason: str | None
    usage: dict[str, Any]
    raw_response: dict[str, Any]

    @property
    def reasoning(self) -> Any:
        return self.message.get("reasoning")

    @property
    def reasoning_details(self) -> Any:
        return self.message.get("reasoning_details")


@dataclass
class LLMCallRecord:
    step: str
    player_id: str
    model: str
    schema_name: str
    request_context: dict[str, Any]
    structured_output: dict[str, Any]
    reasoning_effort: str
    max_tokens: int
    discussion_message_max_chars: int | None = None
    reasoning_summary_max_chars: int | None = None
    exposed_reasoning: Any = None
    exposed_reasoning_details: Any = None
    finish_reason: str | None = None
    usage: dict[str, Any] = field(default_factory=dict)
    validation_error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "step": self.step,
            "player_id": self.player_id,
            "model": self.model,
            "schema_name": self.schema_name,
            "request_context": self.request_context,
            "structured_output": self.structured_output,
            "reasoning_effort": self.reasoning_effort,
            "max_tokens": self.max_tokens,
            "discussion_message_max_chars": self.discussion_message_max_chars,
            "reasoning_summary_max_chars": self.reasoning_summary_max_chars,
            "exposed_reasoning": self.exposed_reasoning,
            "exposed_reasoning_details": self.exposed_reasoning_details,
            "finish_reason": self.finish_reason,
            "usage": self.usage,
            "validation_error": self.validation_error,
        }


class OpenRouterClient:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str = OPENROUTER_API_URL,
        timeout_seconds: float = 90,
        app_title: str = "Ultimate Werewolf Benchmark",
        referer: str | None = None,
    ) -> None:
        self.api_key = api_key or os.environ.get("OPENROUTER_API_KEY")
        if not self.api_key:
            raise OpenRouterError("OPENROUTER_API_KEY is not set")
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.app_title = app_title
        self.referer = referer

    def chat_json(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        schema_name: str,
        schema: dict[str, Any],
        temperature: float = 0.7,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        reasoning_effort: str = DEFAULT_REASONING_EFFORT,
    ) -> dict[str, Any]:
        return self.chat_json_result(
            model=model,
            messages=messages,
            schema_name=schema_name,
            schema=schema,
            temperature=temperature,
            max_tokens=max_tokens,
            reasoning_effort=reasoning_effort,
        ).parsed

    def chat_json_result(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        schema_name: str,
        schema: dict[str, Any],
        temperature: float = 0.7,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        reasoning_effort: str = DEFAULT_REASONING_EFFORT,
    ) -> ChatJSONResult:
        payload = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "reasoning": {"effort": reasoning_effort, "exclude": False},
            "include_reasoning": True,
            "provider": {"require_parameters": True},
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": schema_name,
                    "strict": True,
                    "schema": schema,
                },
            },
        }
        data = self._post_json("/chat/completions", payload)
        try:
            choice = data["choices"][0]
            message = choice["message"]
            content = message["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise OpenRouterError(f"unexpected OpenRouter response shape: {data!r}") from exc
        if content is None:
            finish_reason = choice.get("finish_reason") if isinstance(choice, dict) else None
            raise OpenRouterError(
                f"model {model} returned no JSON content; finish_reason={finish_reason!r}; "
                f"message keys={list(message.keys()) if isinstance(message, dict) else 'unknown'}"
            )
        if isinstance(content, list):
            content = "".join(str(part.get("text", "")) if isinstance(part, dict) else str(part) for part in content)
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            raise OpenRouterError(f"model {model} returned non-JSON content: {content!r}") from exc
        if not isinstance(parsed, dict):
            raise OpenRouterError(f"model {model} returned JSON that is not an object: {parsed!r}")
        usage = data.get("usage", {})
        return ChatJSONResult(
            parsed=parsed,
            message=message if isinstance(message, dict) else {},
            finish_reason=choice.get("finish_reason") if isinstance(choice, dict) else None,
            usage=usage if isinstance(usage, dict) else {},
            raw_response=data,
        )

    def list_models(self, *, supported_parameter: str | None = None, sort: str = "most-popular") -> list[dict[str, Any]]:
        query: dict[str, str] = {"sort": sort}
        if supported_parameter:
            query["supported_parameters"] = supported_parameter
        path = "/models?" + parse.urlencode(query)
        data = self._get_json(path)
        models = data.get("data", [])
        if not isinstance(models, list):
            raise OpenRouterError(f"unexpected models response shape: {data!r}")
        return models

    def _headers(self) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "X-OpenRouter-Title": self.app_title,
        }
        if self.referer:
            headers["HTTP-Referer"] = self.referer
        return headers

    def _post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        req = request.Request(
            self.base_url + path,
            data=json.dumps(payload).encode("utf-8"),
            headers=self._headers(),
            method="POST",
        )
        return self._send(req)

    def _get_json(self, path: str) -> dict[str, Any]:
        req = request.Request(self.base_url + path, headers=self._headers(), method="GET")
        return self._send(req)

    def _send(self, req: request.Request) -> dict[str, Any]:
        try:
            with request.urlopen(req, timeout=self.timeout_seconds) as response:
                raw = response.read().decode("utf-8")
        except error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise OpenRouterError(f"OpenRouter HTTP {exc.code}: {body}") from exc
        except error.URLError as exc:
            raise OpenRouterError(f"OpenRouter request failed: {exc}") from exc
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise OpenRouterError(f"OpenRouter returned invalid JSON: {raw!r}") from exc
        if not isinstance(data, dict):
            raise OpenRouterError(f"OpenRouter returned non-object JSON: {data!r}")
        return data


class OpenRouterAgent(PlayerAgent):
    def __init__(
        self,
        player_id: str,
        *,
        model: str,
        client: OpenRouterClient,
        temperature: float = 0.7,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        reasoning_effort: str = DEFAULT_REASONING_EFFORT,
        discussion_message_max_chars: int = DEFAULT_DISCUSSION_MESSAGE_MAX_CHARS,
        reasoning_summary_max_chars: int = DEFAULT_REASONING_SUMMARY_MAX_CHARS,
    ) -> None:
        self.player_id = player_id
        self.model = model
        self.client = client
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.reasoning_effort = reasoning_effort
        self.discussion_message_max_chars = discussion_message_max_chars
        self.reasoning_summary_max_chars = reasoning_summary_max_chars
        self.call_log: list[LLMCallRecord] = []

    def choose_night_action(self, context: AgentContext) -> NightAction:
        schema = night_action_schema(context)
        validation_error: str | None = None
        for attempt in range(3):
            retry_text = f" Previous attempt was invalid: {validation_error}" if validation_error else ""
            response = self._ask(
                step="night_action",
                context=context,
                schema_name="night_action",
                schema=schema,
                user_prompt=(
                    "Choose your night action. Use only a legal action. "
                    "Use null for fields that do not apply. "
                    "For Troublemaker, target_players must contain exactly two distinct other players."
                    f"{retry_text}"
                ),
            )
            action = NightAction.from_mapping(response)
            try:
                validate_action_for_role(context.current_role, action, context.player_id, context.players)
                return action
            except ValueError as exc:
                validation_error = str(exc)
                self.call_log[-1].validation_error = validation_error
        raise OpenRouterError(f"{self.model} emitted invalid night action after retries: {validation_error}")

    def discuss(self, context: AgentContext) -> DiscussionMessage:
        response = self._ask(
            step="discussion",
            context=context,
            schema_name="discussion_message",
            schema=discussion_schema(
                context,
                message_max_chars=self.discussion_message_max_chars,
                reasoning_summary_max_chars=self.reasoning_summary_max_chars,
            ),
            user_prompt=(
                "It is your turn in the discussion. Speak as your player in one complete message. "
                "You may tell the truth, omit information, bluff, coordinate, or accuse. "
                "Also provide a private reasoning_summary for the benchmark log; it is not shown to other players."
            ),
        )
        return DiscussionMessage(
            speaker=context.player_id,
            round_index=context.round_index,
            message=str(response["message"]),
            claim=response.get("claim"),
            accusation=response.get("accusation"),
        )

    def vote(self, context: AgentContext) -> Vote:
        response = self._ask(
            step="vote",
            context=context,
            schema_name="vote",
            schema=vote_schema(context),
            user_prompt="Vote for exactly one other player. Your vote is simultaneous and final.",
        )
        return Vote(
            voter=context.player_id,
            target_player=str(response["target_player"]),
            reasoning=str(response.get("reasoning") or ""),
        )

    def _ask(
        self,
        *,
        step: str,
        context: AgentContext,
        schema_name: str,
        schema: dict[str, Any],
        user_prompt: str,
    ) -> dict[str, Any]:
        last_error: str | None = None
        for attempt in range(3):
            retry_text = (
                f" Previous response failed validation: {last_error}. Return only a JSON object matching the schema."
                if last_error
                else ""
            )
            request_context = context_payload(context, self.model, user_prompt + retry_text)
            messages = [
                {"role": "system", "content": system_prompt()},
                {"role": "user", "content": json.dumps(request_context, indent=2)},
            ]
            try:
                result = self.client.chat_json_result(
                    model=self.model,
                    messages=messages,
                    schema_name=schema_name,
                    schema=schema,
                    temperature=self.temperature,
                    max_tokens=self.max_tokens,
                    reasoning_effort=self.reasoning_effort,
                )
            except OpenRouterError as exc:
                last_error = str(exc)
                continue
            self.call_log.append(
                LLMCallRecord(
                    step=step,
                    player_id=context.player_id,
                    model=self.model,
                    schema_name=schema_name,
                    request_context=request_context,
                    structured_output=result.parsed,
                    reasoning_effort=self.reasoning_effort,
                    max_tokens=self.max_tokens,
                    discussion_message_max_chars=(
                        self.discussion_message_max_chars if schema_name == "discussion_message" else None
                    ),
                    reasoning_summary_max_chars=(
                        self.reasoning_summary_max_chars if schema_name == "discussion_message" else None
                    ),
                    exposed_reasoning=result.reasoning,
                    exposed_reasoning_details=result.reasoning_details,
                    finish_reason=result.finish_reason,
                    usage=result.usage,
                    validation_error=last_error,
                )
            )
            return result.parsed
        raise OpenRouterError(f"{self.model} failed to return valid structured output after retries: {last_error}")


def system_prompt() -> str:
    return (
        "You are an agent playing One Night Ultimate Werewolf. "
        "Optimize for your current team's win condition, but follow the complete ruleset in the user context "
        "and output schema exactly. You may lie or bluff during discussion. "
        "Never reveal hidden engine state you were not given."
    )


def context_payload(context: AgentContext, model: str, task: str) -> dict[str, Any]:
    return {
        "task": task,
        "model": model,
        "player_id": context.player_id,
        "players": context.players,
        "initial_role": context.initial_role.value,
        "active_role_for_this_step": context.current_role.value,
        "round_index": context.round_index,
        "legal_actions": context.legal_actions,
        "observations": [observation.to_dict() for observation in context.observations],
        "discussion_transcript": [message.to_dict() for message in context.transcript],
        "rules_summary": rules_summary(context),
    }


def rules_summary(context: AgentContext) -> dict[str, Any]:
    return {
        "game_setup": {
            "format": "One Night Ultimate Werewolf, one night followed by discussion and one simultaneous vote.",
            "cards": "There is one card per player plus exactly three face-down center cards.",
            "initial_role": "Your initial_role is the card you woke as and determines whether you act at night.",
            "final_role": (
                "Your final card after all night swaps determines your team and whether you win. "
                "Your final role may differ from your initial role unless an observation tells you."
            ),
            "center_cards": "Center cards are indexed 0, 1, and 2.",
            "doppelganger": "Doppelganger is modeled in code but is not enabled in normal benchmark decks.",
        },
        "night_order": [
            "Doppelganger, only in explicitly enabled experiments",
            "Werewolf",
            "Minion",
            "Mason",
            "Seer",
            "Robber",
            "Troublemaker",
            "Drunk",
            "Insomniac",
        ],
        "role_rules": {
            "Villager": {
                "team": "Village",
                "night": "Does not wake or act.",
                "goal": "Help kill at least one final Werewolf, or if no Werewolves exist, help make sure nobody dies.",
            },
            "Werewolf": {
                "team": "Werewolf",
                "night": (
                    "All initial Werewolves see the list of initial Werewolf players. "
                    "If you are the only initial Werewolf, you may view exactly one center card."
                ),
                "actions": {"with_partners": ["none"], "lone_wolf": ["none", "view_center"]},
                "goal": "Win if at least one final Werewolf exists and no final Werewolf is killed.",
            },
            "Seer": {
                "team": "Village",
                "night": "Choose either one other player to view, or two distinct center cards to view.",
                "actions": {
                    "view_player": "target_player must be exactly one other player, never yourself.",
                    "view_two_center": "center_cards must contain exactly two distinct indices from 0, 1, and 2.",
                },
            },
            "Robber": {
                "team": "Village unless your final card changes teams",
                "night": "Swap your own card with exactly one other player's card, then learn your new role.",
                "actions": {"swap_with_player": "target_player must be one other player, never yourself."},
                "important": "After swapping, you are on the team of the card you took.",
            },
            "Troublemaker": {
                "team": "Village",
                "night": "Swap the cards of exactly two distinct other players. You do not see either card.",
                "actions": {"swap_two_players": "target_players must contain two distinct other players, never yourself."},
            },
            "Drunk": {
                "team": "Village unless your final card changes teams",
                "night": "Swap your own card with exactly one center card without looking at the card you receive.",
                "actions": {"swap_with_center": "center_card must be one index from 0, 1, and 2."},
                "important": "You do not learn your final role from this swap.",
            },
            "Insomniac": {
                "team": "Village unless your final card changed teams",
                "night": "Wake last and learn your own final role after all earlier swaps.",
                "actions": ["none"],
            },
            "Minion": {
                "team": "Minion/Werewolf ally",
                "night": "See the initial Werewolf players. If the list is empty, no player started as Werewolf.",
                "actions": ["none"],
                "goal": (
                    "If any final Werewolf exists, win when no final Werewolf is killed. "
                    "If no final Werewolf exists, win only by surviving while at least one player is killed."
                ),
            },
            "Mason": {
                "team": "Village",
                "night": "See other initial Masons. An empty list means you are the only Mason.",
                "actions": ["none"],
            },
            "Hunter": {
                "team": "Village",
                "night": "Does not wake or act.",
                "special_vote_rule": "If the final Hunter is killed, the player the Hunter voted for also dies.",
            },
            "Tanner": {
                "team": "Tanner",
                "night": "Does not wake or act.",
                "goal": "Win if the final Tanner is killed. Tanner can win alongside another team.",
            },
        },
        "action_rules": {
            "legal_actions_for_this_step": context.legal_actions,
            "night_action_choice": "Use only one of legal_actions_for_this_step. Use null for schema fields that do not apply.",
            "player_targets": "When an action says another player, target one of the listed players other than yourself.",
            "center_targets": "Center-card indices are integers 0, 1, and 2.",
        },
        "discussion_rules": {
            "public_transcript": "discussion_transcript contains only public messages already spoken.",
            "allowed_strategy": "You may tell the truth, omit information, bluff, coordinate, accuse, or defend yourself.",
            "private_information_boundary": (
                "Only use your initial role, observations, and public discussion. "
                "Do not claim hidden engine state as known unless it was in your observations."
            ),
        },
        "vote_rules": {
            "legal_vote_targets": [player for player in context.players if player != context.player_id],
            "self_vote": "You cannot vote for yourself.",
            "simultaneous": "Votes are simultaneous and final.",
            "elimination": (
                "If every player who receives votes receives exactly one vote, nobody dies. "
                "Otherwise, the player or players tied for the most votes die."
            ),
            "hunter": "If the final Hunter dies, the Hunter's vote target also dies.",
        },
        "win_conditions": [
            "Cards after all night swaps are final roles and determine teams.",
            "Village roles win if at least one final Werewolf is killed.",
            "If no final Werewolves exist, Village roles win only if nobody is killed.",
            "Final Werewolves win if at least one final Werewolf exists and no final Werewolf is killed.",
            "Final Minions win with the Werewolves when final Werewolves exist and no final Werewolf is killed.",
            "If no final Werewolves exist, final Minions win only if they survive and at least one player is killed.",
            "Final Tanner wins if the final Tanner is killed, and this does not prevent other eligible teams from also winning.",
        ],
        "current_step": {
            "player_id": context.player_id,
            "initial_role": context.initial_role.value,
            "active_role_for_this_step": context.current_role.value,
            "legal_actions": context.legal_actions,
            "legal_vote_targets": [player for player in context.players if player != context.player_id],
        },
    }


def night_action_schema(context: AgentContext) -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["kind", "target_player", "target_players", "center_card", "center_cards", "reasoning"],
        "properties": {
            "kind": {"type": "string", "enum": context.legal_actions or ["none"]},
            "target_player": {"type": ["string", "null"]},
            "target_players": {
                "type": ["array", "null"],
                "items": {"type": "string"},
            },
            "center_card": {"type": ["integer", "null"]},
            "center_cards": {
                "type": ["array", "null"],
                "items": {"type": "integer"},
            },
            "reasoning": {"type": "string"},
        },
    }


def discussion_schema(
    context: AgentContext,
    *,
    message_max_chars: int = DEFAULT_DISCUSSION_MESSAGE_MAX_CHARS,
    reasoning_summary_max_chars: int = DEFAULT_REASONING_SUMMARY_MAX_CHARS,
) -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["message", "claim", "accusation", "reasoning_summary"],
        "properties": {
            "message": {"type": "string", "minLength": 1, "maxLength": message_max_chars},
            "claim": {"type": ["string", "null"]},
            "accusation": {"type": ["string", "null"]},
            "reasoning_summary": {"type": "string", "maxLength": reasoning_summary_max_chars},
        },
    }


def vote_schema(context: AgentContext) -> dict[str, Any]:
    legal_targets = [player for player in context.players if player != context.player_id]
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["target_player", "reasoning"],
        "properties": {
            "target_player": {"type": "string", "enum": legal_targets},
            "reasoning": {"type": "string"},
        },
    }


def observation_text(observation: Observation) -> str:
    return f"{observation.kind}: {observation.payload}"
