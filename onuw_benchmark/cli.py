from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from onuw_benchmark.agents import MockAgent, PlayerAgent
from onuw_benchmark.engine import DEFAULT_PLAYERS, DEFAULT_ROLE_DECK, GameConfig, OneNightGame, default_role_deck_for_player_count
from onuw_benchmark.openrouter import (
    DEFAULT_DISCUSSION_MESSAGE_MAX_CHARS,
    DEFAULT_MAX_TOKENS,
    DEFAULT_REASONING_EFFORT,
    DEFAULT_REASONING_SUMMARY_MAX_CHARS,
    OpenRouterAgent,
    OpenRouterClient,
    OpenRouterError,
)
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
    run_parser.add_argument(
        "--max-tokens",
        type=int,
        default=DEFAULT_MAX_TOKENS,
        help="max completion tokens for each LLM turn",
    )
    run_parser.add_argument(
        "--reasoning-effort",
        choices=["none", "minimal", "low", "medium", "high", "xhigh", "max"],
        default=DEFAULT_REASONING_EFFORT,
        help="OpenRouter reasoning effort for reasoning-capable models",
    )
    run_parser.add_argument(
        "--discussion-message-max-chars",
        type=int,
        default=DEFAULT_DISCUSSION_MESSAGE_MAX_CHARS,
        help="max public discussion message length requested from each LLM turn",
    )
    run_parser.add_argument(
        "--reasoning-summary-max-chars",
        type=int,
        default=DEFAULT_REASONING_SUMMARY_MAX_CHARS,
        help="max private reasoning_summary length requested from each LLM discussion turn",
    )
    run_parser.add_argument("--openrouter-api-key", default=None, help="OpenRouter API key; defaults to OPENROUTER_API_KEY")
    run_parser.add_argument("--discussion-rounds", type=int, default=3, help="round-robin passes before voting")
    run_parser.add_argument("--seed", type=int, default=None, help="deterministic RNG seed")
    run_parser.add_argument("--runs", type=int, default=1, help="number of games to run and aggregate")
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
    validate_budget_args(args)
    players = resolve_players(args)
    role_deck = [parse_role(role) for role in args.roles] if args.roles else default_role_deck_for_player_count(len(players))
    if args.runs < 1:
        raise ValueError("--runs must be at least 1")
    config = GameConfig(
        players=players,
        role_deck=role_deck,
        discussion_rounds=args.discussion_rounds,
        seed=args.seed,
        allow_doppelganger=args.allow_doppelganger,
    )
    if args.runs > 1:
        return run_multiple_games(args, config)

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


def run_multiple_games(args: argparse.Namespace, base_config: GameConfig) -> int:
    runs: list[dict[str, object]] = []
    for run_index in range(args.runs):
        seed = None if base_config.seed is None else base_config.seed + run_index
        config = GameConfig(
            players=list(base_config.players),
            role_deck=list(base_config.role_deck),
            discussion_rounds=base_config.discussion_rounds,
            seed=seed,
            allow_doppelganger=base_config.allow_doppelganger,
        )
        agents = build_agents(args, config.players)
        result = OneNightGame(config, agents=agents).run()
        run_data = result.to_dict()
        run_data["run_index"] = run_index
        run_data["agents"] = agent_metadata(agents)
        run_data["game_log"] = game_log(result)
        run_data["llm_call_log"] = llm_call_log(agents)
        runs.append(run_data)

    data = {
        "type": "multi_run",
        "run_count": args.runs,
        "provider": args.provider,
        "players": list(base_config.players),
        "role_deck": [role.value for role in base_config.role_deck],
        "discussion_rounds": base_config.discussion_rounds,
        "seed": base_config.seed,
        "runs": runs,
        "summary": summarize_runs(runs, players=base_config.players),
    }
    if args.json:
        print(json.dumps(data, indent=2, sort_keys=True))
        return 0

    print("One Night Ultimate Werewolf benchmark")
    print(f"Runs: {args.runs}")
    print(f"Players: {', '.join(base_config.players)}")
    print()
    print("Win rates by model:")
    for model, stats in sorted(data["summary"]["models"].items()):
        print(format_stats_line(model, stats))
    print()
    print("Win rates by player:")
    for player in base_config.players:
        print(format_stats_line(player, data["summary"]["players"][player]))
    return 0


def summarize_runs(runs: list[dict[str, object]], *, players: list[str]) -> dict[str, object]:
    player_stats = {
        player: {"games": 0, "wins": 0, "win_rate": 0.0, "killed": 0, "killed_rate": 0.0, "model": "unknown"}
        for player in players
    }
    model_stats: dict[str, dict[str, object]] = {}

    for run in runs:
        winners = set(run.get("winners", []))
        killed = set(run.get("killed", []))
        agents = run.get("agents", {})
        if not isinstance(agents, dict):
            agents = {}
        run_players = run.get("players", players)
        if not isinstance(run_players, list):
            run_players = players
        for player in run_players:
            if not isinstance(player, str):
                continue
            player_entry = player_stats.setdefault(
                player,
                {"games": 0, "wins": 0, "win_rate": 0.0, "killed": 0, "killed_rate": 0.0, "model": "unknown"},
            )
            agent = agents.get(player, {})
            model = agent.get("model", "unknown") if isinstance(agent, dict) else "unknown"
            player_entry["model"] = model
            model_entry = model_stats.setdefault(
                str(model),
                {"games": 0, "wins": 0, "win_rate": 0.0, "killed": 0, "killed_rate": 0.0},
            )
            for entry in (player_entry, model_entry):
                entry["games"] = int(entry["games"]) + 1
                if player in winners:
                    entry["wins"] = int(entry["wins"]) + 1
                if player in killed:
                    entry["killed"] = int(entry["killed"]) + 1

    for entry in [*player_stats.values(), *model_stats.values()]:
        games = int(entry["games"])
        entry["win_rate"] = int(entry["wins"]) / games if games else 0.0
        entry["killed_rate"] = int(entry["killed"]) / games if games else 0.0

    return {
        "runs": len(runs),
        "players": player_stats,
        "models": model_stats,
    }


def format_stats_line(label: str, stats: dict[str, object]) -> str:
    games = int(stats["games"])
    wins = int(stats["wins"])
    killed = int(stats["killed"])
    win_rate = float(stats["win_rate"]) * 100
    killed_rate = float(stats["killed_rate"]) * 100
    return f"  {label}: {wins}/{games} wins ({win_rate:.1f}%), killed {killed}/{games} ({killed_rate:.1f}%)"


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
            discussion_message_max_chars=args.discussion_message_max_chars,
            reasoning_summary_max_chars=args.reasoning_summary_max_chars,
        )
        for player, model in zip(players, args.models, strict=True)
    }


def validate_budget_args(args: argparse.Namespace) -> None:
    if args.max_tokens <= 0:
        raise ValueError("--max-tokens must be positive")
    if args.discussion_message_max_chars <= 0:
        raise ValueError("--discussion-message-max-chars must be positive")
    if args.reasoning_summary_max_chars <= 0:
        raise ValueError("--reasoning-summary-max-chars must be positive")


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
