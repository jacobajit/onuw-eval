from __future__ import annotations

import argparse
from datetime import datetime
import html
import json
from pathlib import Path
from typing import Any


def load_run(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"{path} does not contain a JSON object")
    return data


def write_report(input_path: Path, output_path: Path | None = None) -> Path:
    data = load_run(input_path)
    output = output_path or input_path.with_suffix(".html")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_report(data, source_name=str(input_path)), encoding="utf-8")
    return output


def render_report(data: dict[str, Any], *, source_name: str = "run.json") -> str:
    report_data = compact_for_report(data)
    embedded = html.escape(json.dumps(report_data, ensure_ascii=False), quote=False)
    title = html.escape(Path(source_name).name)
    generated = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link rel="icon" href="data:,">
  <title>ONUW Run Browser - {title}</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f7f5ef;
      --ink: #1d2528;
      --muted: #657074;
      --line: #d9d4c9;
      --panel: #ffffff;
      --panel-2: #f0eee7;
      --accent: #8b2f33;
      --accent-2: #1f6b68;
      --warn: #9a5a00;
      --good: #317349;
      --shadow: 0 12px 32px rgba(29, 37, 40, .08);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font: 14px/1.45 ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      color: var(--ink);
      background: var(--bg);
    }}
    header {{
      padding: 26px 28px 18px;
      border-bottom: 1px solid var(--line);
      background: linear-gradient(180deg, #fffdfa, #f4f0e6);
    }}
    h1 {{ margin: 0 0 8px; font-size: 24px; letter-spacing: 0; }}
    h2 {{ margin: 0 0 12px; font-size: 18px; letter-spacing: 0; }}
    h3 {{ margin: 0 0 8px; font-size: 15px; letter-spacing: 0; }}
    .subhead {{ color: var(--muted); display: flex; flex-wrap: wrap; gap: 10px 18px; }}
    .layout {{
      display: grid;
      grid-template-columns: 320px minmax(0, 1fr);
      min-height: calc(100vh - 96px);
    }}
    aside {{
      border-right: 1px solid var(--line);
      padding: 18px;
      background: #fbfaf6;
      position: sticky;
      top: 0;
      align-self: start;
      height: calc(100vh - 96px);
      overflow: auto;
    }}
    main {{ padding: 22px; min-width: 0; }}
    .section {{ margin-bottom: 22px; }}
    .panel {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: var(--shadow);
      padding: 16px;
    }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; }}
    .player {{
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 12px;
      background: var(--panel);
    }}
    .player.winner {{ border-color: rgba(49, 115, 73, .5); background: #f4fbf4; }}
    .player.killed {{ border-color: rgba(139, 47, 51, .55); }}
    .player-head {{ display: flex; justify-content: space-between; gap: 10px; align-items: start; }}
    .pid {{ font-weight: 800; font-size: 16px; }}
    .model {{ color: var(--muted); font-size: 12px; overflow-wrap: anywhere; }}
    .role-row {{ margin-top: 8px; display: grid; grid-template-columns: 72px 1fr; gap: 4px 8px; }}
    .label {{ color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: .04em; }}
    .badge {{
      display: inline-flex;
      align-items: center;
      min-height: 22px;
      border-radius: 999px;
      padding: 2px 8px;
      border: 1px solid var(--line);
      background: var(--panel-2);
      font-size: 12px;
      font-weight: 700;
      white-space: nowrap;
    }}
    .badge.good {{ border-color: rgba(49, 115, 73, .4); color: var(--good); background: #eef8ef; }}
    .badge.bad {{ border-color: rgba(139, 47, 51, .4); color: var(--accent); background: #fbefef; }}
    nav {{ display: grid; gap: 8px; }}
    nav button, .toggle button {{
      appearance: none;
      border: 1px solid var(--line);
      background: var(--panel);
      color: var(--ink);
      border-radius: 8px;
      padding: 9px 10px;
      text-align: left;
      cursor: pointer;
      font: inherit;
    }}
    nav button.active, .toggle button.active {{
      border-color: var(--accent-2);
      background: #e8f3f2;
      color: #0e4d4a;
      font-weight: 800;
    }}
    .toggle {{ display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 12px; }}
    .timeline {{ display: grid; gap: 12px; }}
    .event {{
      border: 1px solid var(--line);
      border-left: 5px solid var(--accent-2);
      border-radius: 8px;
      background: var(--panel);
      padding: 12px;
    }}
    .event.night {{ border-left-color: #58508d; }}
    .event.discussion {{ border-left-color: var(--accent-2); }}
    .event.vote {{ border-left-color: var(--warn); }}
    .event.resolution {{ border-left-color: var(--good); }}
    .event-head {{ display: flex; flex-wrap: wrap; gap: 8px; align-items: center; justify-content: space-between; margin-bottom: 8px; }}
    .event-title {{ font-weight: 800; }}
    .event-meta {{ color: var(--muted); font-size: 12px; }}
    .text {{ white-space: pre-wrap; overflow-wrap: anywhere; }}
    details {{
      margin-top: 10px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fbfaf6;
      padding: 8px 10px;
    }}
    summary {{ cursor: pointer; font-weight: 800; }}
    pre {{
      margin: 10px 0 0;
      white-space: pre-wrap;
      overflow-wrap: anywhere;
      background: #222729;
      color: #f6f1e7;
      border-radius: 8px;
      padding: 12px;
      max-height: 420px;
      overflow: auto;
      font-size: 12px;
    }}
    .calls {{ display: grid; gap: 12px; }}
    .call {{
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      padding: 12px;
    }}
    .call.validation {{ border-color: rgba(154, 90, 0, .5); }}
    .two-col {{ display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }}
    .kv {{ display: grid; grid-template-columns: 130px minmax(0, 1fr); gap: 6px 10px; }}
    .muted {{ color: var(--muted); }}
    .cost {{ font-variant-numeric: tabular-nums; }}
    @media (max-width: 900px) {{
      .layout {{ grid-template-columns: 1fr; }}
      aside {{ position: static; height: auto; border-right: 0; border-bottom: 1px solid var(--line); }}
      .two-col {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <header>
    <h1>One Night Ultimate Werewolf Run</h1>
    <div class="subhead">
      <span>Source: {html.escape(source_name)}</span>
      <span>Generated: {html.escape(generated)}</span>
      <span id="summaryLine"></span>
    </div>
  </header>
  <div class="layout">
    <aside>
      <div class="section">
        <h2>Views</h2>
        <nav id="nav"></nav>
      </div>
      <div class="section">
        <h2>Players</h2>
        <div id="sidePlayers"></div>
      </div>
    </aside>
    <main>
      <section id="overview" class="section"></section>
      <section id="timeline" class="section" hidden></section>
      <section id="discussion" class="section" hidden></section>
      <section id="reasoning" class="section" hidden></section>
      <section id="raw" class="section" hidden></section>
    </main>
  </div>
  <script id="run-data" type="application/json">{embedded}</script>
  <script>
    const DATA = JSON.parse(document.getElementById('run-data').textContent);
    const views = ['overview', 'timeline', 'discussion', 'reasoning', 'raw'];
    const viewLabels = {{
      overview: 'Overview',
      timeline: 'Full Timeline',
      discussion: 'Discussion',
      reasoning: 'Model Thoughts',
      raw: 'Raw JSON'
    }};

    function esc(value) {{
      return String(value ?? '').replace(/[&<>"']/g, ch => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[ch]));
    }}
    function asJSON(value) {{ return esc(JSON.stringify(value, null, 2)); }}
    function playerModel(player) {{
      return DATA.agents?.[player]?.model || 'mock';
    }}
    function displayName(player) {{
      if (DATA.agents?.[player]?.model) return DATA.agents[player].model;
      return player;
    }}
    function playerSubtext(player) {{
      return DATA.agents?.[player]?.provider || '';
    }}
    function replacePlayerIds(value) {{
      let text = String(value ?? '');
      for (const player of (DATA.players || [])) {{
        const re = new RegExp(`\\\\b${{player.replace(/[.*+?^${{}}()|[\\]\\\\]/g, '\\\\$&')}}\\\\b`, 'g');
        text = text.replace(re, displayName(player));
      }}
      return text;
    }}
    function displayText(value) {{
      return esc(replacePlayerIds(value));
    }}
    function role(player, which) {{
      return DATA[which + '_roles']?.[player] || 'unknown';
    }}
    function playerBadge(player, cls='') {{ return `<span class="badge ${{cls}}">${{esc(displayName(player))}}</span>`; }}
    function badge(text, cls='') {{ return `<span class="badge ${{cls}}">${{esc(text)}}</span>`; }}
    function costForUsage(usage) {{
      if (!usage) return '';
      if (usage.cost !== undefined) return `$${{Number(usage.cost).toFixed(5)}}`;
      return '';
    }}
    function reasoningText(call) {{
      const parts = [];
      const out = call.structured_output || {{}};
      if (out.reasoning_summary) parts.push(['Model reasoning summary', out.reasoning_summary]);
      if (out.reasoning) parts.push(['Structured reasoning', out.reasoning]);
      if (call.exposed_reasoning) parts.push(['Provider-exposed reasoning', call.exposed_reasoning]);
      const details = (call.exposed_reasoning_details || []).filter(item => item && item.type !== 'reasoning.encrypted');
      for (const item of details) {{
        parts.push([item.type || 'Reasoning detail', item.summary || item.text || JSON.stringify(item)]);
      }}
      const encryptedCount = (call.exposed_reasoning_details || []).filter(item => item && item.type === 'reasoning.encrypted').length;
      if (encryptedCount) parts.push(['Encrypted reasoning payloads', `${{encryptedCount}} encrypted provider payload(s) omitted from display`]);
      return parts;
    }}
    function eventHTML(event) {{
      const phase = event.phase || 'event';
      let title = phase;
      let body = '';
      if (phase === 'night') {{
        title = `${{displayName(event.player)}} night action as ${{event.role}}`;
        body = `<div class="kv"><div class="label">Action</div><div>${{esc(event.action?.kind)}}</div><div class="label">Reasoning</div><div class="text">${{displayText(event.action?.reasoning || '')}}</div></div>`;
        if (event.observations?.length) body += `<details><summary>Observations</summary><pre>${{displayText(JSON.stringify(event.observations, null, 2))}}</pre></details>`;
      }} else if (phase === 'discussion') {{
        title = `${{displayName(event.speaker)}} speaks`;
        body = `<div class="text">${{displayText(event.message)}}</div>`;
        if (event.claim || event.accusation) body += `<div style="margin-top:8px">${{event.claim ? badge('claims ' + event.claim) : ''}} ${{event.accusation ? playerBadge(event.accusation, 'bad') : ''}}</div>`;
      }} else if (phase === 'vote') {{
        title = `${{displayName(event.voter)}} votes ${{displayName(event.target_player)}}`;
        body = `<div class="text">${{displayText(event.reasoning || '')}}</div>`;
      }} else if (phase === 'resolution') {{
        title = 'Resolution';
        body = `<div class="kv"><div class="label">Killed</div><div>${{(event.killed || []).map(p => playerBadge(p, 'bad')).join(' ') || 'Nobody'}}</div><div class="label">Winners</div><div>${{(event.winners || []).map(p => playerBadge(p, 'good')).join(' ') || 'None'}}</div></div><details><summary>Winner reasons</summary><pre>${{displayText(JSON.stringify(event.winner_reasons || {{}}, null, 2))}}</pre></details>`;
      }}
      return `<article class="event ${{esc(phase)}}"><div class="event-head"><div class="event-title">${{esc(title)}}</div><div class="event-meta">${{esc(phase)}} #${{esc(event.index ?? '')}}</div></div>${{body}}</article>`;
    }}
    function playerCard(player) {{
      const killed = DATA.killed?.includes(player);
      const winner = DATA.winners?.includes(player);
      return `<div class="player ${{winner ? 'winner' : ''}} ${{killed ? 'killed' : ''}}">
        <div class="player-head"><div><div class="pid">${{esc(displayName(player))}}</div><div class="model">${{esc(playerSubtext(player))}}</div></div><div>${{winner ? badge('winner','good') : ''}} ${{killed ? badge('killed','bad') : ''}}</div></div>
        <div class="role-row"><div class="label">Initial</div><div>${{esc(role(player, 'initial'))}}</div><div class="label">Final</div><div>${{esc(role(player, 'final'))}}</div></div>
      </div>`;
    }}
    function renderOverview() {{
      const players = DATA.players || Object.keys(DATA.final_roles || {{}});
      const votes = (DATA.votes || []).map(v => `<tr><td>${{esc(displayName(v.voter))}}</td><td>${{esc(displayName(v.target_player))}}</td><td>${{displayText(v.reasoning || '')}}</td></tr>`).join('');
      document.getElementById('overview').innerHTML = `
        <div class="section panel">
          <h2>Result</h2>
          <div class="grid">
            <div><div class="label">Killed</div><div>${{(DATA.killed || []).map(p => playerBadge(p, 'bad')).join(' ') || 'Nobody'}}</div></div>
            <div><div class="label">Winners</div><div>${{(DATA.winners || []).map(p => playerBadge(p, 'good')).join(' ') || 'None'}}</div></div>
            <div><div class="label">Seed</div><div>${{esc(DATA.seed)}}</div></div>
            <div><div class="label">Discussion rounds</div><div>${{esc(DATA.discussion_rounds)}}</div></div>
          </div>
          <details open><summary>Winner reasons</summary><pre>${{displayText(JSON.stringify(DATA.winner_reasons || {{}}, null, 2))}}</pre></details>
        </div>
        <div class="section">
          <h2>Role Assignments</h2>
          <div class="grid">${{players.map(playerCard).join('')}}</div>
        </div>
        <div class="section panel">
          <h2>Center Cards</h2>
          <div class="two-col"><div><div class="label">Initial center</div><div>${{(DATA.initial_center || []).map(x => badge(x)).join(' ')}}</div></div><div><div class="label">Final center</div><div>${{(DATA.final_center || []).map(x => badge(x)).join(' ')}}</div></div></div>
        </div>
        <div class="section panel">
          <h2>Votes</h2>
          <div style="overflow:auto"><table style="width:100%; border-collapse:collapse"><thead><tr><th align="left">Voter</th><th align="left">Target</th><th align="left">Reason</th></tr></thead><tbody>${{votes}}</tbody></table></div>
        </div>`;
    }}
    function renderTimeline() {{
      const filters = ['all', 'night', 'discussion', 'vote', 'resolution'];
      document.getElementById('timeline').innerHTML = `<h2>Full Timeline</h2><div class="toggle">${{filters.map((f,i)=>`<button data-filter="${{f}}" class="${{i===0?'active':''}}">${{esc(f)}}</button>`).join('')}}</div><div class="timeline" id="timelineList"></div>`;
      const list = document.getElementById('timelineList');
      const draw = filter => {{ list.innerHTML = (DATA.game_log || []).filter(e => filter === 'all' || e.phase === filter).map(eventHTML).join(''); }};
      draw('all');
      document.querySelectorAll('#timeline button').forEach(btn => btn.addEventListener('click', () => {{
        document.querySelectorAll('#timeline button').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        draw(btn.dataset.filter);
      }}));
    }}
    function renderDiscussion() {{
      document.getElementById('discussion').innerHTML = `<h2>Public Discussion</h2><div class="timeline">${{(DATA.transcript || []).map(e => eventHTML({{phase:'discussion', ...e}})).join('')}}</div>`;
    }}
    function renderReasoning() {{
      const calls = DATA.llm_call_log || {{}};
      const blocks = Object.entries(calls).map(([player, list]) => `
        <div class="section">
          <h2>${{esc(displayName(player))}}</h2>
          <div class="calls">${{list.map((call, i) => callHTML(call, i)).join('')}}</div>
        </div>`).join('');
      document.getElementById('reasoning').innerHTML = blocks || '<div class="panel">No LLM call log found.</div>';
    }}
    function callHTML(call, index) {{
      const thoughts = reasoningText(call);
      const usage = call.usage || {{}};
      return `<article class="call ${{call.validation_error ? 'validation' : ''}}">
        <div class="event-head"><div class="event-title">${{esc(call.step)}} #${{index + 1}}</div><div class="event-meta">${{esc(call.finish_reason || '')}} ${{costForUsage(usage) ? ' · ' + esc(costForUsage(usage)) : ''}}</div></div>
        <div class="kv">
          <div class="label">Schema</div><div>${{esc(call.schema_name)}}</div>
          <div class="label">Reasoning</div><div>${{esc(call.reasoning_effort || '')}}</div>
          <div class="label">Tokens</div><div>${{esc(usage.total_tokens ?? '')}}</div>
          ${{call.validation_error ? `<div class="label">Validation</div><div class="text">${{displayText(call.validation_error)}}</div>` : ''}}
        </div>
        <details open><summary>Decision</summary><pre>${{displayText(JSON.stringify(call.structured_output || {{}}, null, 2))}}</pre></details>
        ${{thoughts.length ? `<details open><summary>Thoughts and reasoning</summary>${{thoughts.map(([label, text]) => `<h3>${{esc(label)}}</h3><div class="text">${{displayText(text)}}</div>`).join('')}}</details>` : ''}}
        <details><summary>Prompt context</summary><pre>${{displayText(JSON.stringify(call.request_context || {{}}, null, 2))}}</pre></details>
        <details><summary>Usage</summary><pre>${{asJSON(usage)}}</pre></details>
      </article>`;
    }}
    function renderRaw() {{
      document.getElementById('raw').innerHTML = `<h2>Raw Report Data</h2><div class="panel"><pre>${{asJSON(DATA)}}</pre></div>`;
    }}
    function switchView(view) {{
      for (const id of views) document.getElementById(id).hidden = id !== view;
      document.querySelectorAll('nav button').forEach(btn => btn.classList.toggle('active', btn.dataset.view === view));
      location.hash = view;
    }}
    function init() {{
      const nav = document.getElementById('nav');
      nav.innerHTML = views.map(v => `<button data-view="${{v}}">${{viewLabels[v]}}</button>`).join('');
      nav.querySelectorAll('button').forEach(btn => btn.addEventListener('click', () => switchView(btn.dataset.view)));
      const players = DATA.players || Object.keys(DATA.final_roles || {{}});
      document.getElementById('sidePlayers').innerHTML = players.map(playerCard).join('');
      document.getElementById('summaryLine').textContent = `${{players.length}} players · killed: ${{(DATA.killed || []).map(displayName).join(', ') || 'nobody'}} · winners: ${{(DATA.winners || []).map(displayName).join(', ') || 'none'}}`;
      renderOverview();
      renderTimeline();
      renderDiscussion();
      renderReasoning();
      renderRaw();
      const initial = views.includes(location.hash.slice(1)) ? location.hash.slice(1) : 'overview';
      switchView(initial);
    }}
    init();
  </script>
</body>
</html>
"""


def compact_for_report(data: dict[str, Any]) -> dict[str, Any]:
    compacted = json.loads(json.dumps(data))
    for calls in compacted.get("llm_call_log", {}).values():
        for call in calls:
            details = call.get("exposed_reasoning_details")
            if isinstance(details, list):
                call["exposed_reasoning_details"] = [compact_reasoning_detail(detail) for detail in details]
    return compacted


def compact_reasoning_detail(detail: Any) -> Any:
    if not isinstance(detail, dict):
        return detail
    if detail.get("type") == "reasoning.encrypted":
        data = detail.get("data", "")
        return {
            "type": "reasoning.encrypted",
            "id": detail.get("id"),
            "format": detail.get("format"),
            "omitted": True,
            "bytes": len(data) if isinstance(data, str) else None,
        }
    return detail


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="onuw-report")
    parser.add_argument("input", type=Path, help="run JSON file")
    parser.add_argument("--output", "-o", type=Path, default=None, help="HTML output path")
    args = parser.parse_args(argv)
    output = write_report(args.input, args.output)
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
