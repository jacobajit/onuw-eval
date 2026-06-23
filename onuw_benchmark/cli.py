from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from onuw_benchmark.agents import MockAgent, PlayerAgent
from onuw_benchmark.engine import DEFAULT_PLAYERS, DEFAULT_ROLE_DECK, GameConfig, OneNightGame, default_role_deck_for_player_count
from onuw_benchmark.openrouter import OpenRouterAgent, OpenRouterClient, OpenRouterError
from onuw_benchmark.report import write_report
from onuw_benchmark.roles import parse_role


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="onuw-benchmark")
    subparsers = parser.add_subparsers(dest="command")

    run_parser = subparsers.add_parser("run", help="run one benchmark game")
    run_parser.add_argument("--players", nargs="+", default=None, help="player ids")
    run_parser.add_argument(
        "--roles",
        nargs="+",
        default=None,
        help="role deck; must be players + 3 cards",
    )
    run_parser.add_argument("--provider", choices=["mock", "openrouter"], default="mock", help="agent provider")
    run_parser.add_argument("--models", nargs="+", default=None, help="one model slug per player for provider-backed agents")
    run_parser.add_argument("--temperature", type=float, default=0.7, help="LLM sampling temperature")
    run_parser.add_argument("--max-tokens", type=int, default=4000, help="max completion tokens for each LLM turn")
    run_parser.add_argument(
        "--reasoning-effort",
        choices=["none", "minimal", "low", "medium", "high", "xhigh", "max"],
        default="medium",
        help="OpenRouter reasoning effort for reasoning-capable models",
    )
    run_parser.add_argument("--openrouter-api-key", default=None, help="OpenRouter API key; defaults to OPENROUTER_API_KEY")
    run_parser.add_argument("--discussion-rounds", type=int, default=3, help="round-robin passes before voting")
    run_parser.add_argument("--seed", type=int, default=None, help="deterministic RNG seed")
    run_parser.add_argument("--json", action="store_true", help="print full JSON result")
    run_parser.add_argument(
        "--allow-doppelganger",
        action="store_true",
        help="allow experimental Doppelganger decks; not recommended for benchmark runs yet",
    )

    report_parser = subparsers.add_parser("report", help="render an HTML browser for a run JSON")
    report_parser.add_argument("input", help="run JSON file")
    report_parser.add_argument("--output", "-o", default=None, help="HTML output path")
    return parser


def run_command(args: argparse.Namespace) -> int:
    players = resolve_players(args)
    role_deck = [parse_role(role) for role in args.roles] if args.roles else default_role_deck_for_player_count(len(players))
    config = GameConfig(
        players=players,
        role_deck=role_deck,
        discussion_rounds=args.discussion_rounds,
        seed=args.seed,
        allow_doppelganger=args.allow_doppelganger,
    )
    agents = build_agents(args, config.players)
    result = OneNightGame(config, agents=agents).run()
    if args.json:
        data = result.to_dict()
        data["agents"] = agent_metadata(agents)
        data["game_log"] = game_log(result)
        data["llm_call_log"] = llm_call_log(agents)
        print(json.dumps(data, indent=2, sort_keys=True))
        return 0

    print("One Night Ultimate Werewolf game")
    print(f"Players: {', '.join(result.config.players)}")
    if args.provider == "openrouter":
        print("Models:")
        for player in result.config.players:
            agent = agents[player]
            print(f"  {player}: {getattr(agent, 'model', 'unknown')}")
    print(f"Killed: {', '.join(result.killed) if result.killed else 'nobody'}")
    print(f"Winners: {', '.join(result.winners) if result.winners else 'none'}")
    print()
    print("Initial roles:")
    for player, role in result.initial_roles.items():
        print(f"  {player}: {role.value}")
    print("Final roles:")
    for player, role in result.final_roles.items():
        print(f"  {player}: {role.value}")
    print("Votes:")
    for vote in result.votes:
        print(f"  {vote.voter} -> {vote.target_player}")
    return 0


def resolve_players(args: argparse.Namespace) -> list[str]:
    if args.players:
        return list(args.players)
    if args.provider == "openrouter" and args.models:
        return [f"P{i + 1}" for i in range(len(args.models))]
    return list(DEFAULT_PLAYERS)


def build_agents(args: argparse.Namespace, players: list[str]) -> dict[str, PlayerAgent]:
    if args.provider == "mock":
        return {player: MockAgent(player) for player in players}
    if not args.models:
        raise ValueError("--models is required when --provider openrouter")
    if len(args.models) != len(players):
        raise ValueError("--models must contain exactly one model slug per player")
    client = OpenRouterClient(api_key=args.openrouter_api_key)
    return {
        player: OpenRouterAgent(
            player,
            model=model,
            client=client,
            temperature=args.temperature,
            max_tokens=args.max_tokens,
            reasoning_effort=args.reasoning_effort,
        )
        for player, model in zip(players, args.models, strict=True)
    }


def agent_metadata(agents: dict[str, PlayerAgent]) -> dict[str, dict[str, str]]:
    data: dict[str, dict[str, str]] = {}
    for player, agent in agents.items():
        model = getattr(agent, "model", None)
        data[player] = {
            "provider": "openrouter" if model else "mock",
            "model": str(model) if model else "mock",
        }
    return data


def llm_call_log(agents: dict[str, PlayerAgent]) -> dict[str, list[dict[str, object]]]:
    logs: dict[str, list[dict[str, object]]] = {}
    for player, agent in agents.items():
        call_log = getattr(agent, "call_log", [])
        logs[player] = [record.to_dict() if hasattr(record, "to_dict") else dict(record) for record in call_log]
    return logs


def game_log(result: object) -> list[dict[str, object]]:
    events: list[dict[str, object]] = []
    night_events = getattr(result, "night_events")
    transcript = getattr(result, "transcript")
    votes = getattr(result, "votes")
    killed = getattr(result, "killed")
    winners = getattr(result, "winners")
    winner_reasons = getattr(result, "winner_reasons")

    for index, event in enumerate(night_events):
        events.append({"phase": "night", "index": index, **event.to_dict()})
    for index, message in enumerate(transcript):
        events.append({"phase": "discussion", "index": index, **message.to_dict()})
    for index, vote in enumerate(votes):
        events.append({"phase": "vote", "index": index, **vote.to_dict()})
    events.append({"phase": "resolution", "index": 0, "killed": killed, "winners": winners, "winner_reasons": winner_reasons})
    return events


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    raw_args = list(sys.argv[1:] if argv is None else argv)
    if not raw_args or raw_args[0].startswith("-"):
        raw_args = ["run", *raw_args]
    args = parser.parse_args(raw_args)
    if args.command == "run":
        try:
            return run_command(args)
        except (OpenRouterError, ValueError) as exc:
            parser.exit(1, f"error: {exc}\n")
    if args.command == "report":
        output = write_report(Path(args.input), Path(args.output) if args.output else None)
        print(output)
        return 0
    parser.error(f"unknown command {args.command!r}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
