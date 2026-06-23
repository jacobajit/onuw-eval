from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
import json
import random
from typing import Any

from onuw_benchmark.agents import AgentContext, MockAgent, Observation, PlayerAgent
from onuw_benchmark.roles import Role, SUPPORTED_NIGHT_ACTION_ROLES, WAKE_ORDER, parse_role
from onuw_benchmark.schemas import DiscussionMessage, NightAction, Vote, validate_action_for_role, validate_vote


DEFAULT_PLAYERS = ["Alice", "Bob", "Carol", "Dana"]
DEFAULT_ROLE_DECK = [
    Role.WEREWOLF,
    Role.SEER,
    Role.ROBBER,
    Role.TROUBLEMAKER,
    Role.VILLAGER,
    Role.VILLAGER,
    Role.DRUNK,
]


def default_role_deck_for_player_count(player_count: int) -> list[Role]:
    if player_count < 3 or player_count > 10:
        raise ValueError("One Night Ultimate Werewolf supports 3-10 players")
    deck = [
        Role.WEREWOLF,
        Role.SEER,
        Role.ROBBER,
        Role.TROUBLEMAKER,
        Role.VILLAGER,
        Role.VILLAGER,
        Role.DRUNK,
    ]
    extras = [
        Role.WEREWOLF,
        Role.MINION,
        Role.MASON,
        Role.MASON,
        Role.INSOMNIAC,
        Role.HUNTER,
        Role.TANNER,
    ]
    needed = player_count + 3
    while len(deck) < needed:
        deck.append(extras[len(deck) - len(DEFAULT_ROLE_DECK)])
    return deck[:needed]


@dataclass(frozen=True)
class GameConfig:
    players: list[str] = field(default_factory=lambda: list(DEFAULT_PLAYERS))
    role_deck: list[Role] = field(default_factory=lambda: list(DEFAULT_ROLE_DECK))
    discussion_rounds: int = 3
    seed: int | None = None
    allow_doppelganger: bool = False

    def __post_init__(self) -> None:
        normalized_players = [str(player) for player in self.players]
        normalized_roles = [parse_role(role) for role in self.role_deck]
        object.__setattr__(self, "players", normalized_players)
        object.__setattr__(self, "role_deck", normalized_roles)
        if len(set(normalized_players)) != len(normalized_players):
            raise ValueError("player ids must be unique")
        if len(normalized_players) < 3 or len(normalized_players) > 10:
            raise ValueError("One Night Ultimate Werewolf supports 3-10 players")
        if len(normalized_roles) != len(normalized_players) + 3:
            raise ValueError("role deck must contain exactly three more cards than players")
        if self.discussion_rounds < 0:
            raise ValueError("discussion_rounds must be non-negative")
        if not self.allow_doppelganger and Role.DOPPELGANGER in normalized_roles:
            raise ValueError("Doppelganger is modeled but not enabled; pass allow_doppelganger=True only for experiments")


@dataclass
class NightEvent:
    role: Role
    player: str
    action: NightAction
    observations: list[Observation] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "role": self.role.value,
            "player": self.player,
            "action": self.action.to_dict(),
            "observations": [observation.to_dict() for observation in self.observations],
        }


@dataclass
class GameResult:
    config: GameConfig
    initial_roles: dict[str, Role]
    initial_center: list[Role]
    final_roles: dict[str, Role]
    final_center: list[Role]
    night_events: list[NightEvent]
    observations: dict[str, list[Observation]]
    transcript: list[DiscussionMessage]
    votes: list[Vote]
    killed: list[str]
    winners: list[str]
    winner_reasons: dict[str, str]

    def to_dict(self, *, include_private: bool = True) -> dict[str, Any]:
        data: dict[str, Any] = {
            "players": self.config.players,
            "discussion_rounds": self.config.discussion_rounds,
            "seed": self.config.seed,
            "final_roles": {player: role.value for player, role in self.final_roles.items()},
            "final_center": [role.value for role in self.final_center],
            "night_events": [event.to_dict() for event in self.night_events],
            "observations": {
                player: [observation.to_dict() for observation in player_observations]
                for player, player_observations in self.observations.items()
            },
            "transcript": [message.to_dict() for message in self.transcript],
            "votes": [vote.to_dict() for vote in self.votes],
            "killed": self.killed,
            "winners": self.winners,
            "winner_reasons": self.winner_reasons,
        }
        if include_private:
            data["initial_roles"] = {player: role.value for player, role in self.initial_roles.items()}
            data["initial_center"] = [role.value for role in self.initial_center]
        return data

    def to_json(self, *, include_private: bool = True, indent: int = 2) -> str:
        return json.dumps(self.to_dict(include_private=include_private), indent=indent, sort_keys=True)


class OneNightGame:
    def __init__(self, config: GameConfig, agents: dict[str, PlayerAgent] | None = None) -> None:
        self.config = config
        self.rng = random.Random(config.seed)
        self.agents = agents or {player: MockAgent(player) for player in config.players}
        missing = set(config.players) - set(self.agents)
        if missing:
            raise ValueError(f"missing agents for players: {sorted(missing)}")

    def run(self) -> GameResult:
        initial_roles, initial_center = self._deal()
        table = dict(initial_roles)
        center = list(initial_center)
        observations: dict[str, list[Observation]] = {player: [] for player in self.config.players}
        night_events = self._run_night(initial_roles, table, center, observations)
        transcript = self._run_discussion(initial_roles, table, observations)
        votes = self._run_votes(initial_roles, table, observations, transcript)
        killed = self._resolve_killed(votes, table)
        winners, winner_reasons = self._resolve_winners(table, killed)

        return GameResult(
            config=self.config,
            initial_roles=initial_roles,
            initial_center=initial_center,
            final_roles=table,
            final_center=center,
            night_events=night_events,
            observations=observations,
            transcript=transcript,
            votes=votes,
            killed=killed,
            winners=winners,
            winner_reasons=winner_reasons,
        )

    def _deal(self) -> tuple[dict[str, Role], list[Role]]:
        deck = list(self.config.role_deck)
        self.rng.shuffle(deck)
        player_cards = deck[: len(self.config.players)]
        center_cards = deck[len(self.config.players) :]
        return dict(zip(self.config.players, player_cards, strict=True)), center_cards

    def _run_night(
        self,
        initial_roles: dict[str, Role],
        table: dict[str, Role],
        center: list[Role],
        observations: dict[str, list[Observation]],
    ) -> list[NightEvent]:
        events: list[NightEvent] = []
        for role in WAKE_ORDER:
            if role == Role.DOPPELGANGER and not self.config.allow_doppelganger:
                continue
            actors = [player for player in self.config.players if initial_roles[player] == role]
            if role == Role.WEREWOLF:
                self._werewolf_group_info(actors, center, observations)
            elif role == Role.MINION:
                self._minion_info(actors, initial_roles, observations)
            elif role == Role.MASON:
                self._mason_info(actors, observations)
            elif role == Role.INSOMNIAC:
                self._insomniac_info(actors, table, observations)

            for player in actors:
                if role not in SUPPORTED_NIGHT_ACTION_ROLES:
                    continue
                legal_actions = self._legal_action_names(role, lone_wolf=(role == Role.WEREWOLF and len(actors) == 1))
                context = self._context(
                    player,
                    initial_roles,
                    observations,
                    acting_role=role,
                    legal_actions=legal_actions,
                )
                action = self.agents[player].choose_night_action(context)
                if action.kind not in legal_actions:
                    raise ValueError(f"{player} emitted illegal {role.value} action {action.kind}; legal actions: {legal_actions}")
                validate_action_for_role(role, action, player, self.config.players)
                event_observations = self._apply_action(role, player, action, table, center)
                observations[player].extend(event_observations)
                events.append(NightEvent(role=role, player=player, action=action, observations=event_observations))
        return events

    def _werewolf_group_info(
        self,
        actors: list[str],
        center: list[Role],
        observations: dict[str, list[Observation]],
    ) -> None:
        for player in actors:
            observations[player].append(
                Observation(
                    kind="werewolf_partners",
                    payload={"werewolves": actors, "is_lone_wolf": len(actors) == 1},
                )
            )
        if len(actors) == 1:
            player = actors[0]
            observations[player].append(
                Observation(kind="lone_wolf_available_center_cards", payload={"center_cards": [0, 1, 2]})
            )

    def _minion_info(
        self,
        actors: list[str],
        initial_roles: dict[str, Role],
        observations: dict[str, list[Observation]],
    ) -> None:
        werewolves = [player for player, role in initial_roles.items() if role == Role.WEREWOLF]
        for player in actors:
            observations[player].append(Observation(kind="minion_sees_werewolves", payload={"werewolves": werewolves}))

    def _mason_info(self, actors: list[str], observations: dict[str, list[Observation]]) -> None:
        for player in actors:
            observations[player].append(
                Observation(kind="mason_partners", payload={"masons": [actor for actor in actors if actor != player]})
            )

    def _insomniac_info(
        self,
        actors: list[str],
        table: dict[str, Role],
        observations: dict[str, list[Observation]],
    ) -> None:
        for player in actors:
            observations[player].append(
                Observation(kind="insomniac_final_role", payload={"player": player, "role": table[player].value})
            )

    def _apply_action(
        self,
        role: Role,
        player: str,
        action: NightAction,
        table: dict[str, Role],
        center: list[Role],
    ) -> list[Observation]:
        if action.kind == "none":
            return []
        if role == Role.WEREWOLF and action.kind == "view_center":
            return [Observation(kind="werewolf_view_center", payload={"center_card": action.center_card, "role": center[action.center_card].value})]
        if role == Role.SEER and action.kind == "view_player":
            target = action.target_player
            return [Observation(kind="seer_view_player", payload={"player": target, "role": table[target].value})]
        if role == Role.SEER and action.kind == "view_two_center":
            cards = list(action.center_cards or ())
            return [
                Observation(
                    kind="seer_view_two_center",
                    payload={"center_cards": cards, "roles": [center[index].value for index in cards]},
                )
            ]
        if role == Role.ROBBER and action.kind == "swap_with_player":
            target = action.target_player
            table[player], table[target] = table[target], table[player]
            return [Observation(kind="robber_new_role", payload={"player": player, "role": table[player].value, "swapped_with": target})]
        if role == Role.TROUBLEMAKER and action.kind == "swap_two_players":
            first, second = action.target_players or ("", "")
            table[first], table[second] = table[second], table[first]
            return [Observation(kind="troublemaker_swapped", payload={"players": [first, second]})]
        if role == Role.DRUNK and action.kind == "swap_with_center":
            index = action.center_card
            table[player], center[index] = center[index], table[player]
            return [Observation(kind="drunk_swapped_center", payload={"center_card": index, "looked": False})]
        raise ValueError(f"unhandled action application for {role.value}: {action}")

    def _run_discussion(
        self,
        initial_roles: dict[str, Role],
        table: dict[str, Role],
        observations: dict[str, list[Observation]],
    ) -> list[DiscussionMessage]:
        transcript: list[DiscussionMessage] = []
        for round_index in range(self.config.discussion_rounds):
            for player in self.config.players:
                context = self._context(
                    player,
                    initial_roles,
                    observations,
                    transcript=transcript,
                    round_index=round_index,
                )
                message = self.agents[player].discuss(context)
                if message.speaker != player:
                    raise ValueError(f"agent {player} emitted discussion as {message.speaker}")
                if not message.message.strip():
                    raise ValueError(f"agent {player} emitted empty discussion message")
                transcript.append(message)
        return transcript

    def _run_votes(
        self,
        initial_roles: dict[str, Role],
        table: dict[str, Role],
        observations: dict[str, list[Observation]],
        transcript: list[DiscussionMessage],
    ) -> list[Vote]:
        votes: list[Vote] = []
        for player in self.config.players:
            context = self._context(player, initial_roles, observations, transcript=transcript)
            vote = self.agents[player].vote(context)
            validate_vote(vote, self.config.players)
            votes.append(vote)
        return votes

    def _resolve_killed(self, votes: list[Vote], table: dict[str, Role]) -> list[str]:
        counts = Counter(vote.target_player for vote in votes)
        if counts and all(count == 1 for count in counts.values()):
            killed: set[str] = set()
        else:
            max_votes = max(counts.values(), default=0)
            killed = {player for player, count in counts.items() if count == max_votes}

        hunter_votes = {vote.voter: vote.target_player for vote in votes}
        for player in list(killed):
            if table[player] == Role.HUNTER:
                killed.add(hunter_votes[player])
        return sorted(killed, key=self.config.players.index)

    def _resolve_winners(self, table: dict[str, Role], killed: list[str]) -> tuple[list[str], dict[str, str]]:
        killed_set = set(killed)
        werewolves = [player for player, role in table.items() if role == Role.WEREWOLF]
        killed_werewolves = [player for player in werewolves if player in killed_set]
        any_player_killed = bool(killed)
        reasons: dict[str, str] = {}
        winners: set[str] = set()

        for player, role in table.items():
            if role == Role.TANNER and player in killed_set:
                winners.add(player)
                reasons[player] = "Tanner was killed"

        if killed_werewolves:
            for player, role in table.items():
                if role not in {Role.WEREWOLF, Role.MINION, Role.TANNER}:
                    winners.add(player)
                    reasons[player] = "Village team killed at least one Werewolf"
        elif werewolves:
            for player, role in table.items():
                if role == Role.WEREWOLF:
                    winners.add(player)
                    reasons[player] = "Werewolf survived the vote"
                elif role == Role.MINION:
                    winners.add(player)
                    reasons[player] = "Minion wins because no Werewolf was killed"
        elif not any_player_killed:
            for player, role in table.items():
                if role not in {Role.MINION, Role.TANNER}:
                    winners.add(player)
                    reasons[player] = "No players were Werewolves and nobody was killed"
        else:
            for player, role in table.items():
                if role == Role.MINION and player not in killed_set:
                    winners.add(player)
                    reasons[player] = "No Werewolves were present and Minion survived while a villager died"

        return sorted(winners, key=self.config.players.index), reasons

    def _context(
        self,
        player: str,
        initial_roles: dict[str, Role],
        observations: dict[str, list[Observation]],
        *,
        acting_role: Role | None = None,
        transcript: list[DiscussionMessage] | None = None,
        round_index: int = 0,
        legal_actions: list[str] | None = None,
    ) -> AgentContext:
        return AgentContext(
            player_id=player,
            players=list(self.config.players),
            initial_role=initial_roles[player],
            current_role=acting_role or initial_roles[player],
            observations=list(observations[player]),
            transcript=list(transcript or []),
            round_index=round_index,
            legal_actions=list(legal_actions or []),
        )

    def _legal_action_names(self, role: Role, *, lone_wolf: bool = False) -> list[str]:
        return {
            Role.WEREWOLF: ["none", "view_center"] if lone_wolf else ["none"],
            Role.MINION: ["none"],
            Role.MASON: ["none"],
            Role.SEER: ["view_player", "view_two_center"],
            Role.ROBBER: ["swap_with_player"],
            Role.TROUBLEMAKER: ["swap_two_players"],
            Role.DRUNK: ["swap_with_center"],
            Role.INSOMNIAC: ["none"],
        }.get(role, ["none"])
