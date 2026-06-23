from __future__ import annotations

import unittest

from onuw_benchmark.agents import AgentContext
from onuw_benchmark.engine import GameConfig, OneNightGame
from onuw_benchmark.roles import Role
from onuw_benchmark.schemas import DiscussionMessage, NightAction, Vote


class FixedAgent:
    def __init__(self, player_id: str, action: NightAction | None = None, vote_target: str | None = None) -> None:
        self.player_id = player_id
        self.action = action or NightAction()
        self.vote_target = vote_target

    def choose_night_action(self, context: AgentContext) -> NightAction:
        return self.action

    def discuss(self, context: AgentContext) -> DiscussionMessage:
        return DiscussionMessage(speaker=self.player_id, round_index=context.round_index, message="test")

    def vote(self, context: AgentContext) -> Vote:
        target = self.vote_target or next(player for player in context.players if player != self.player_id)
        return Vote(voter=self.player_id, target_player=target)


class RecordingAgent(FixedAgent):
    def __init__(self, player_id: str, action: NightAction | None = None, vote_target: str | None = None) -> None:
        super().__init__(player_id, action, vote_target)
        self.discussion_contexts: list[AgentContext] = []

    def discuss(self, context: AgentContext) -> DiscussionMessage:
        self.discussion_contexts.append(context)
        return super().discuss(context)


class EngineTests(unittest.TestCase):
    def test_troublemaker_swaps_two_other_players(self) -> None:
        players = ["A", "B", "C"]
        roles = [Role.TROUBLEMAKER, Role.WEREWOLF, Role.VILLAGER, Role.SEER, Role.ROBBER, Role.DRUNK]
        config = GameConfig(players=players, role_deck=roles, seed=0, discussion_rounds=0)
        game = OneNightGame(
            config,
            agents={
                "A": FixedAgent("A", NightAction(kind="swap_two_players", target_players=("B", "C")), "B"),
                "B": FixedAgent("B", vote_target="A"),
                "C": FixedAgent("C", vote_target="A"),
            },
        )
        initial = {"A": Role.TROUBLEMAKER, "B": Role.WEREWOLF, "C": Role.VILLAGER}
        center = [Role.SEER, Role.ROBBER, Role.DRUNK]
        events = game._run_night(initial, initial.copy(), center, {player: [] for player in players})
        self.assertEqual(events[-1].action.kind, "swap_two_players")

    def test_hunter_kills_voted_target_when_hunter_dies(self) -> None:
        players = ["A", "B", "C"]
        config = GameConfig(
            players=players,
            role_deck=[Role.HUNTER, Role.WEREWOLF, Role.VILLAGER, Role.SEER, Role.ROBBER, Role.DRUNK],
            seed=0,
        )
        game = OneNightGame(config)
        table = {"A": Role.HUNTER, "B": Role.WEREWOLF, "C": Role.VILLAGER}
        votes = [Vote("A", "B"), Vote("B", "A"), Vote("C", "A")]
        self.assertEqual(game._resolve_killed(votes, table), ["A", "B"])

    def test_everyone_gets_one_vote_means_nobody_dies(self) -> None:
        players = ["A", "B", "C"]
        config = GameConfig(
            players=players,
            role_deck=[Role.VILLAGER, Role.VILLAGER, Role.SEER, Role.ROBBER, Role.DRUNK, Role.TROUBLEMAKER],
            seed=0,
        )
        game = OneNightGame(config)
        table = {"A": Role.VILLAGER, "B": Role.SEER, "C": Role.ROBBER}
        votes = [Vote("A", "B"), Vote("B", "C"), Vote("C", "A")]
        self.assertEqual(game._resolve_killed(votes, table), [])

    def test_village_wins_when_no_werewolves_and_nobody_dies(self) -> None:
        players = ["A", "B", "C"]
        config = GameConfig(
            players=players,
            role_deck=[Role.VILLAGER, Role.VILLAGER, Role.SEER, Role.ROBBER, Role.DRUNK, Role.TROUBLEMAKER],
            seed=0,
        )
        game = OneNightGame(config)
        winners, reasons = game._resolve_winners({"A": Role.VILLAGER, "B": Role.SEER, "C": Role.ROBBER}, [])
        self.assertEqual(winners, ["A", "B", "C"])
        self.assertIn("A", reasons)

    def test_tanner_and_village_can_both_win_if_tanner_and_werewolf_die(self) -> None:
        players = ["A", "B", "C"]
        config = GameConfig(players=players, role_deck=[Role.TANNER, Role.WEREWOLF, Role.SEER, Role.ROBBER, Role.DRUNK, Role.VILLAGER])
        game = OneNightGame(config)
        winners, _ = game._resolve_winners({"A": Role.TANNER, "B": Role.WEREWOLF, "C": Role.SEER}, ["A", "B"])
        self.assertEqual(winners, ["A", "C"])

    def test_discussion_context_does_not_reveal_hidden_final_role(self) -> None:
        players = ["A", "B", "C"]
        config = GameConfig(
            players=players,
            role_deck=[Role.ROBBER, Role.WEREWOLF, Role.VILLAGER, Role.SEER, Role.DRUNK, Role.TROUBLEMAKER],
            discussion_rounds=1,
        )
        agent_a = RecordingAgent("A", NightAction(kind="swap_with_player", target_player="B"), "B")
        game = OneNightGame(
            config,
            agents={
                "A": agent_a,
                "B": RecordingAgent("B", vote_target="A"),
                "C": RecordingAgent("C", vote_target="A"),
            },
        )
        observations = {player: [] for player in players}
        initial = {"A": Role.ROBBER, "B": Role.WEREWOLF, "C": Role.VILLAGER}
        table = initial.copy()
        game._run_night(initial, table, [Role.SEER, Role.DRUNK, Role.TROUBLEMAKER], observations)
        self.assertEqual(table["A"], Role.WEREWOLF)
        game._run_discussion(initial, table, observations)
        self.assertEqual(agent_a.discussion_contexts[0].current_role, Role.ROBBER)

    def test_multiple_werewolves_cannot_peek_at_center(self) -> None:
        players = ["A", "B", "C"]
        config = GameConfig(
            players=players,
            role_deck=[Role.WEREWOLF, Role.WEREWOLF, Role.VILLAGER, Role.SEER, Role.DRUNK, Role.TROUBLEMAKER],
        )
        game = OneNightGame(
            config,
            agents={
                "A": FixedAgent("A", NightAction(kind="view_center", center_card=0), "B"),
                "B": FixedAgent("B", vote_target="A"),
                "C": FixedAgent("C", vote_target="A"),
            },
        )
        with self.assertRaises(ValueError):
            game._run_night(
                {"A": Role.WEREWOLF, "B": Role.WEREWOLF, "C": Role.VILLAGER},
                {"A": Role.WEREWOLF, "B": Role.WEREWOLF, "C": Role.VILLAGER},
                [Role.SEER, Role.DRUNK, Role.TROUBLEMAKER],
                {player: [] for player in players},
            )


if __name__ == "__main__":
    unittest.main()
