#!/usr/bin/env python3
"""Render balance/index.html from balance/summary.json."""
from __future__ import annotations
import argparse, json
from pathlib import Path

def esc(t):
    return str(t).replace("&","&amp;").replace("<","&lt;").replace(">","&gt;").replace('"',"&quot;")

def pill(text, kind=""):
    return f'<span class="pill {kind}">{esc(text)}</span>' if text else ""

def pct(n, d):
    return "—" if not d else f"{n}/{d} ({100*n/d:.0f}%)"

def kind_cells(ctr):
    ctr = ctr or {}
    parts=[]
    for k,cls in (("burn","died"),("stop","timeout"),("none","")):
        v=int(ctr.get(k,0))
        parts.append(pill(f"{k} {v}", cls if v else ""))
    for k,v in ctr.items():
        if k not in ("burn","stop","none"):
            parts.append(pill(f"{k} {v}"))
    return " ".join(parts)

def oc_cell(oc):
    oc=oc or {}
    bits=[]
    if oc.get("cleared"): bits.append(pill(f"cleared {oc['cleared']}","ok"))
    if oc.get("died"): bits.append(pill(f"died {oc['died']}","died"))
    if oc.get("timeout"): bits.append(pill(f"timeout {oc['timeout']}","timeout"))
    if oc.get("left_room"): bits.append(pill(f"left {oc['left_room']}","open"))
    return " ".join(bits) or "—"

def matrix_table(block, kind):
    matrix=block.get("matrix") or {}
    heroes=[]
    for recs in matrix.values():
        for h in recs:
            if h not in heroes: heroes.append(h)
    rows=[]
    for skill, recs in matrix.items():
        cells=[f"<th>{esc(skill)}</th>"]
        for hero in heroes:
            rec=(recs or {}).get(hero) or {}
            n=rec.get("n",0); c=rec.get("cleared",0); d=rec.get("died",0); t=rec.get("timeout",0)
            label=[]
            if c: label.append(f'<span class="ok">{c}/{n} clear</span>')
            if d: label.append(f'<span class="bad">{d}/{n} died</span>')
            if t: label.append(f'<span class="warn">{t}/{n} timeout</span>')
            extra=""
            if kind=="boss" and rec.get("boss_hp_end"):
                ends=rec["boss_hp_end"]
                extra=f'<div class="muted">boss HP end {min(ends)}–{max(ends)}</div>'
            cells.append(f"<td>{'<br>'.join(label) or '—'}{extra}</td>")
        rows.append("<tr>"+"".join(cells)+"</tr>")
    head="<tr><th>Skill</th>"+"".join(f"<th>{esc(h)}</th>" for h in heroes)+"</tr>"
    return f'<div class="table-wrap"><table class="runs-table"><thead>{head}</thead><tbody>{"".join(rows)}</tbody></table></div>'

def subset_row(name, b):
    b=b or {}
    return (f"<tr><th>{esc(name)}</th><td>{b.get('n',0)}</td>"
            f"<td>{pct(b.get('died',0), b.get('n',0))}</td>"
            f"<td>{oc_cell(b.get('outcomes') or {})}</td>"
            f"<td>{kind_cells(b.get('death_kind'))}</td>"
            f"<td>lands {b.get('lands_gt0','—')} / harmful {b.get('harmful_gt0','—')} / DoT {b.get('dot_gt0','—')}</td></tr>")

def kv_rows(mapping):
    rows=[]
    for name, rec in (mapping or {}).items():
        rows.append(f"<tr><th>{esc(name)}</th><td>{rec.get('n',0)}</td>"
                    f"<td>{pct(rec.get('died',0), rec.get('n',0))}</td>"
                    f"<td>{oc_cell(rec.get('outcomes') or {})}</td>"
                    f"<td>{kind_cells(rec.get('death_kind'))}</td></tr>")
    return "".join(rows)

def arena_section(diff, a):
    boss, entry = a.get("boss") or {}, a.get("entry") or {}
    bo, eo = boss.get("outcomes") or {}, entry.get("outcomes") or {}
    return f"""
<section>
  <h2>Cinder Rex and stage-3 entry — {esc(diff.title())}</h2>
  <div class="stats">
    <div class="stat"><b>{pct(bo.get('cleared',0), boss.get('n',0))}</b><span>Cinder Rex clears</span></div>
    <div class="stat"><b>{pct(bo.get('died',0), boss.get('n',0))}</b><span>Cinder Rex deaths</span></div>
    <div class="stat"><b>{boss.get('status_harmful',0)}</b><span>harmful status lands in the fight</span></div>
    <div class="stat"><b>{pct(eo.get('died',0), entry.get('n',0))}</b><span>entry-foyer deaths</span></div>
  </div>
  <p class="meta">5 heroes × bot / skilled / average × 4 seeds. Cinder Rex starts at 240 HP.
     Arena slices in this sweep landed no harmful statuses; deaths are contact or burst.
     The entry foyer is the stage-3 door, not a curated Burn/Stop room.</p>
  <h3>Cinder Rex matrix</h3>
  {matrix_table(boss, "boss")}
  <h3>Stage-3 entry foyer</h3>
  {matrix_table(entry, "entry")}
</section>
"""

def rooms_section(diff, r):
    oc=r.get("outcomes") or {}
    all_row={"n": r.get("n"), "died": r.get("deaths"), "outcomes": oc, "death_kind": r.get("death_kind"),
             "lands_gt0": "—", "harmful_gt0": "—", "dot_gt0": "—"}
    chain=r.get("death_chain") or {}
    chain_html=" ".join(pill(f"{k} {v}", "timeout" if ("dot" in k or "stop" in k) else "") for k,v in chain.items())
    return f"""
<section>
  <h2>Stage-3 combat rooms — {esc(diff.title())}</h2>
  <div class="stats">
    <div class="stat"><b>{r.get('n',0)}</b><span>fights</span></div>
    <div class="stat"><b>{pct(r.get('deaths',0), r.get('n',0))}</b><span>deaths</span></div>
    <div class="stat"><b>{(r.get('death_kind') or {}).get('burn',0)}</b><span>Burn deaths</span></div>
    <div class="stat"><b>{(r.get('death_kind') or {}).get('stop',0)}</b><span>Stop deaths</span></div>
  </div>
  <p class="meta">Official <code>balance_rooms.py</code>: 80 fixtures per difficulty (Cinder Maw / Cinder Kite and Fold Star packs included)
     × 3 skills × 2 seeds = 480 fights. Death kind is the status at death.
     Burn carriers: Cinder Maw (14), Cinder Kite (25). Stop carrier: Fold Star (11).</p>
  <h3>By room type</h3>
  <div class="table-wrap"><table class="runs-table">
    <thead><tr><th>Subset</th><th>N</th><th>Deaths</th><th>Outcomes</th><th>Death kind</th><th>Status landings</th></tr></thead>
    <tbody>
      {subset_row("All rooms", all_row)}
      {subset_row("Cinder Maw / Kite (14, 25)", r.get("cinder"))}
      {subset_row("Fold Star / Stop (11)", r.get("fold_star"))}
      {subset_row("No 11 / 14 / 25", r.get("no_status_carriers"))}
    </tbody>
  </table></div>
  <h3>By skill</h3>
  <div class="table-wrap"><table class="runs-table">
    <thead><tr><th>Skill</th><th>N</th><th>Deaths</th><th>Outcomes</th><th>Death kind</th></tr></thead>
    <tbody>{kv_rows(r.get("by_skill"))}</tbody>
  </table></div>
  <h3>By hero</h3>
  <div class="table-wrap"><table class="runs-table">
    <thead><tr><th>Hero</th><th>N</th><th>Deaths</th><th>Outcomes</th><th>Death kind</th></tr></thead>
    <tbody>{kv_rows(r.get("by_hero"))}</tbody>
  </table></div>
  <p class="meta">Death chains: {chain_html or "—"}.
     <code>dot_pinned_then_hit</code> is the #217 floor (DoT stops at 1 HP, then a hit finishes the run).
     <code>stop_then_hit</code> is a Stop proc followed by a hit while frozen.</p>
</section>
"""

def page(summary):
    arena, rooms = summary.get("arena") or {}, summary.get("rooms") or {}
    build, sha = summary.get("build") or "", summary.get("rom_sha256") or ""
    commit=f"https://github.com/struktured-labs/quintra/commit/{build}"
    easy_b=(arena.get("easy") or {}).get("boss") or {}
    norm_b=(arena.get("normal") or {}).get("boss") or {}
    norm_r=rooms.get("normal") or {}
    notes="".join(f"<li>{esc(n)}</li>" for n in (summary.get("notes") or []))
    body=f"""
<header>
  <p class="meta"><a href="../index.html">&larr; All runs</a></p>
  <h1>Stage 3 balance summary</h1>
  <p>Death breakdown and Cinder Rex matrix on current main
     <a href="{esc(commit)}"><code>{esc(build)}</code></a>.
     Official human-skill bots (no deep RL). ROM sha256
     <code>{esc(sha[:16])}&hellip;</code>. No ROM downloads.</p>
</header>
<main>
  <div class="stats">
    <div class="stat"><b>{pct((easy_b.get("outcomes") or {}).get("cleared",0), easy_b.get("n",0))}</b><span>Easy Cinder Rex clears</span></div>
    <div class="stat"><b>{pct((norm_b.get("outcomes") or {}).get("died",0), norm_b.get("n",0))}</b><span>Normal Cinder Rex deaths</span></div>
    <div class="stat"><b>{pct((norm_r.get("death_kind") or {}).get("burn",0), norm_r.get("deaths",0))}</b><span>of Normal room deaths are Burn</span></div>
    <div class="stat"><b>{pct((norm_r.get("death_kind") or {}).get("stop",0), norm_r.get("deaths",0))}</b><span>of Normal room deaths are Stop</span></div>
  </div>
  {arena_section("easy", arena.get("easy") or {})}
  {arena_section("normal", arena.get("normal") or {})}
  {rooms_section("easy", rooms.get("easy") or {})}
  {rooms_section("normal", rooms.get("normal") or {})}
  <section>
    <h2>How to read this</h2>
    <ul>{notes}</ul>
    <p class="meta">Source: <a href="summary.json"><code>summary.json</code></a>.
       Generated from official <code>balance_arena.py</code> and <code>balance_rooms.py</code> CSVs.</p>
  </section>
</main>
"""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Stage 3 balance summary — Quintra runs</title>
  <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@500;600&amp;family=IBM+Plex+Sans:wght@400;600&amp;display=swap">
  <link rel="stylesheet" href="../styles.css">
</head>
<body>
{body}
<footer>
  Quintra playtest log. Screenshots and video only — no ROM downloads.
</footer>
</body>
</html>
"""

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--summary", type=Path, default=Path("balance/summary.json"))
    ap.add_argument("--out", type=Path, default=Path("balance/index.html"))
    args=ap.parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(page(json.loads(args.summary.read_text())))
    print(f"wrote {args.out}")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
