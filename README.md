# Ultimate Werewolf Benchmark

This is a local benchmark harness for One Night Ultimate Werewolf agents. It runs a complete single-night game with:

- role assignment from a `players + 3 center cards` deck
- role-specific night actions
- configurable round-robin discussion
- simultaneous voting
- official-style elimination and win-condition resolution
- structured JSON outputs for night actions, discussion messages, votes, and game results

The LLM layer is intentionally mocked for now. Replace `MockAgent` or implement `PlayerAgent` when API keys and provider choices are ready.

## Supported Rules

The default harness supports the base One Night Ultimate Werewolf roles:

- Villager
- Werewolf, including lone-wolf center-card peek
- Seer
- Robber
- Troublemaker
- Drunk
- Insomniac
- Minion
- Mason
- Hunter
- Tanner

`Doppelganger` is represented in the role enum and schema but is not enabled in the default role set yet because its full interaction with copied roles and later card movement needs a dedicated test matrix. Keep it out of benchmark decks until that module is finished.

Vote resolution follows the common ONUW rule: if every player receives exactly one vote, nobody dies; otherwise the player or players tied for most votes die. If the Hunter dies, the player the Hunter voted for also dies.

## Quick Start

Run a deterministic mock game:

```bash
python3 -m onuw_benchmark run --seed 7 --discussion-rounds 3
```

Emit machine-readable JSON:

```bash
python3 -m onuw_benchmark run --seed 7 --json
```

Use custom players and role deck:

```bash
python3 -m onuw_benchmark run \
  --players Alice Bob Carol Dana \
  --roles Werewolf Seer Robber Troublemaker Villager Villager Drunk \
  --discussion-rounds 3 \
  --reasoning-effort medium \
  --seed 11 \
  --json
```

The role deck must contain exactly three more roles than players.

## OpenRouter Models

Set an OpenRouter key and provide one model slug per player:

```bash
export OPENROUTER_API_KEY="..."

python3 -m onuw_benchmark run \
  --provider openrouter \
  --models \
    openai/gpt-5.5 \
    anthropic/claude-opus-4.8 \
    google/gemini-3.5-flash \
    x-ai/grok-4.3 \
    deepseek/deepseek-v4-pro \
  --discussion-rounds 3 \
  --seed 11 \
  --json
```

If you omit `--players`, the harness creates `P1`, `P2`, etc. Matching model slugs to current frontier models is intentionally a CLI choice because model availability changes quickly. OpenRouter exposes the live model catalog at `https://openrouter.ai/api/v1/models`.

The OpenRouter adapter uses strict JSON-schema outputs for night actions, discussion messages, and votes. It also sets `provider.require_parameters=true` so OpenRouter should reject providers that cannot honor the structured-output request.

JSON results include:

- `night_events`, `transcript`, `votes`, and resolution fields
- `game_log`, a chronological merged event stream
- `llm_call_log`, with each model call's request context, structured output, final decision fields, usage, finish reason, requested reasoning effort, provider-exposed reasoning fields, and model-supplied reasoning summaries

The harness requests `reasoning.effort=medium` by default. Hidden chain of thought cannot be retrieved if a provider does not expose it; in that case the log records the final structured reasoning fields and leaves `exposed_reasoning` / `exposed_reasoning_details` empty.

## Development

Run tests:

```bash
python3 -m unittest discover -s tests
```

Render a browsable HTML report for a completed JSON run:

```bash
python3 -m onuw_benchmark report results/onuw_openrouter_20260623_015008.json
```

The report is written next to the JSON file with a `.html` extension.

Core extension points:

- `onuw_benchmark.agents.PlayerAgent`: implement this for provider-backed LLM agents.
- `onuw_benchmark.schemas`: structured output schemas and validators.
- `onuw_benchmark.engine.OneNightGame`: deterministic game runner.
