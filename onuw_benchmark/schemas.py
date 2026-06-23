from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from onuw_benchmark.roles import Role

ActionKind = Literal[
    "none",
    "view_player",
    "view_center",
    "view_two_center",
    "swap_with_player",
    "swap_two_players",
    "swap_with_center",
]


ACTION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["kind"],
    "properties": {
        "kind": {
            "type": "string",
            "enum": [
                "none",
                "view_player",
                "view_center",
                "view_two_center",
                "swap_with_player",
                "swap_two_players",
                "swap_with_center",
            ],
        },
        "target_player": {"type": "string"},
        "target_players": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 2,
            "maxItems": 2,
        },
        "center_card": {"type": "integer", "minimum": 0, "maximum": 2},
        "center_cards": {
            "type": "array",
            "items": {"type": "integer", "minimum": 0, "maximum": 2},
            "minItems": 2,
            "maxItems": 2,
        },
        "reasoning": {"type": "string"},
    },
}

DISCUSSION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["message"],
    "properties": {
        "message": {"type": "string", "minLength": 1},
        "claim": {"type": "string"},
        "accusation": {"type": "string"},
        "reasoning_summary": {"type": "string"},
    },
}

VOTE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["target_player"],
    "properties": {
        "target_player": {"type": "string"},
        "reasoning": {"type": "string"},
    },
}


@dataclass(frozen=True)
class NightAction:
    kind: ActionKind = "none"
    target_player: str | None = None
    target_players: tuple[str, str] | None = None
    center_card: int | None = None
    center_cards: tuple[int, int] | None = None
    reasoning: str = ""

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> "NightAction":
        kind = value.get("kind", "none")
        if kind not in ACTION_SCHEMA["properties"]["kind"]["enum"]:
            raise ValueError(f"invalid action kind: {kind!r}")
        target_players = value.get("target_players")
        center_cards = value.get("center_cards")
        return cls(
            kind=kind,
            target_player=value.get("target_player"),
            target_players=tuple(target_players) if target_players is not None else None,
            center_card=value.get("center_card"),
            center_cards=tuple(center_cards) if center_cards is not None else None,
            reasoning=value.get("reasoning", ""),
        )

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {"kind": self.kind}
        if self.target_player is not None:
            data["target_player"] = self.target_player
        if self.target_players is not None:
            data["target_players"] = list(self.target_players)
        if self.center_card is not None:
            data["center_card"] = self.center_card
        if self.center_cards is not None:
            data["center_cards"] = list(self.center_cards)
        if self.reasoning:
            data["reasoning"] = self.reasoning
        return data


@dataclass(frozen=True)
class DiscussionMessage:
    speaker: str
    round_index: int
    message: str
    claim: str | None = None
    accusation: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data = {"speaker": self.speaker, "round_index": self.round_index, "message": self.message}
        if self.claim:
            data["claim"] = self.claim
        if self.accusation:
            data["accusation"] = self.accusation
        return data


@dataclass(frozen=True)
class Vote:
    voter: str
    target_player: str
    reasoning: str = ""

    def to_dict(self) -> dict[str, Any]:
        data = {"voter": self.voter, "target_player": self.target_player}
        if self.reasoning:
            data["reasoning"] = self.reasoning
        return data


def validate_action_for_role(
    role: Role,
    action: NightAction,
    player_id: str,
    players: list[str],
    *,
    allow_none: bool = True,
) -> None:
    if action.kind == "none" and allow_none:
        return

    def require_player(target: str | None, *, allow_self: bool = False) -> str:
        if target is None:
            raise ValueError(f"{action.kind} requires target_player")
        if target not in players:
            raise ValueError(f"unknown target player: {target}")
        if not allow_self and target == player_id:
            raise ValueError(f"{role.value} cannot target self with {action.kind}")
        return target

    def require_center(index: int | None) -> int:
        if index is None:
            raise ValueError(f"{action.kind} requires center_card")
        if index < 0 or index > 2:
            raise ValueError(f"center_card must be 0, 1, or 2; got {index}")
        return index

    if role == Role.SEER:
        if action.kind == "view_player":
            require_player(action.target_player)
            return
        if action.kind == "view_two_center":
            if action.center_cards is None or len(set(action.center_cards)) != 2:
                raise ValueError("Seer view_two_center requires two distinct center_cards")
            for center_card in action.center_cards:
                require_center(center_card)
            return
    elif role == Role.ROBBER and action.kind == "swap_with_player":
        require_player(action.target_player)
        return
    elif role == Role.TROUBLEMAKER and action.kind == "swap_two_players":
        if action.target_players is None or len(set(action.target_players)) != 2:
            raise ValueError("Troublemaker requires two distinct target_players")
        for target in action.target_players:
            require_player(target)
        return
    elif role == Role.DRUNK and action.kind == "swap_with_center":
        require_center(action.center_card)
        return
    elif role == Role.WEREWOLF and action.kind in {"view_center", "none"}:
        if action.kind == "view_center":
            require_center(action.center_card)
        return
    elif role in {Role.MINION, Role.MASON, Role.INSOMNIAC} and action.kind == "none":
        return

    raise ValueError(f"{role.value} cannot perform action {action.kind}")


def validate_vote(vote: Vote, players: list[str]) -> None:
    if vote.voter not in players:
        raise ValueError(f"unknown voter: {vote.voter}")
    if vote.target_player not in players:
        raise ValueError(f"unknown vote target: {vote.target_player}")
    if vote.voter == vote.target_player:
        raise ValueError("players cannot vote for themselves")
