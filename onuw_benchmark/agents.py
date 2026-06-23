from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from onuw_benchmark.roles import Role
from onuw_benchmark.schemas import DiscussionMessage, NightAction, Vote


@dataclass(frozen=True)
class Observation:
    kind: str
    payload: dict[str, object]

    def to_text(self) -> str:
        return f"{self.kind}: {self.payload}"

    def to_dict(self) -> dict[str, object]:
        return {"kind": self.kind, "payload": self.payload}


@dataclass(frozen=True)
class AgentContext:
    player_id: str
    players: list[str]
    initial_role: Role
    current_role: Role
    observations: list[Observation] = field(default_factory=list)
    transcript: list[DiscussionMessage] = field(default_factory=list)
    round_index: int = 0
    legal_actions: list[str] = field(default_factory=list)


class PlayerAgent(Protocol):
    player_id: str

    def choose_night_action(self, context: AgentContext) -> NightAction:
        ...

    def discuss(self, context: AgentContext) -> DiscussionMessage:
        ...

    def vote(self, context: AgentContext) -> Vote:
        ...


class MockAgent:
    """Deterministic agent used until provider-backed LLM agents are plugged in."""

    def __init__(self, player_id: str) -> None:
        self.player_id = player_id

    def choose_night_action(self, context: AgentContext) -> NightAction:
        others = [player for player in context.players if player != context.player_id]
        role = context.current_role
        if role == Role.SEER:
            return NightAction(kind="view_player", target_player=others[0], reasoning="mock seer checks first other player")
        if role == Role.ROBBER:
            return NightAction(kind="swap_with_player", target_player=others[0], reasoning="mock robber swaps with first other player")
        if role == Role.TROUBLEMAKER:
            return NightAction(
                kind="swap_two_players",
                target_players=(others[0], others[1]),
                reasoning="mock troublemaker swaps first two other players",
            )
        if role == Role.DRUNK:
            return NightAction(kind="swap_with_center", center_card=0, reasoning="mock drunk takes center 0")
        if role == Role.WEREWOLF:
            if "view_center" in context.legal_actions:
                return NightAction(kind="view_center", center_card=0, reasoning="mock lone wolf checks center 0")
            return NightAction(kind="none", reasoning="mock werewolf has partners and does not peek")
        return NightAction(kind="none")

    def discuss(self, context: AgentContext) -> DiscussionMessage:
        obs = "; ".join(observation.to_text() for observation in context.observations[-2:])
        if obs:
            msg = f"I started as {context.initial_role.value}. My useful info: {obs}."
        else:
            msg = f"I started as {context.initial_role.value}. I do not have hard night information."
        return DiscussionMessage(
            speaker=context.player_id,
            round_index=context.round_index,
            message=msg,
            claim=context.initial_role.value,
        )

    def vote(self, context: AgentContext) -> Vote:
        known_wolves: list[str] = []
        for observation in context.observations:
            if observation.kind in {"seer_view_player", "robber_new_role", "insomniac_final_role"}:
                target = observation.payload.get("player") or context.player_id
                role = observation.payload.get("role")
                if role == Role.WEREWOLF.value and target != context.player_id:
                    known_wolves.append(str(target))
            if observation.kind == "werewolf_partners":
                partners = observation.payload.get("werewolves", [])
                if isinstance(partners, list):
                    known_wolves.extend(str(player) for player in partners if player != context.player_id)

        if context.initial_role == Role.TANNER:
            target = next(player for player in context.players if player != context.player_id)
            return Vote(voter=context.player_id, target_player=target, reasoning="mock tanner votes arbitrarily")

        if known_wolves:
            return Vote(voter=context.player_id, target_player=known_wolves[0], reasoning="mock votes for observed werewolf")

        target = next(player for player in context.players if player != context.player_id)
        return Vote(voter=context.player_id, target_player=target, reasoning="mock default first legal target")
