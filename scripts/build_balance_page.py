#!/usr/bin/env python3
"""Render balance/index.html from balance/summary.json.

Accepts a single-build v1 summary or a compare-v1 document that keeps a
baseline (684bac5c) next to a newer build.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path


def esc(t):
    return str(t).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def pill(text, kind=""):
    return f'<span class="pill {kind}">{esc(text)}</span>' if text else ""


def pct(n, d):
    return "—" if not d else f"{n}/{d} ({100 * n / d:.0f}%)"


def commit_url(sha):
    short = (sha or "")[:12]
    if not sha:
        return "", ""
    return f"https://github.com/struktured-labs/quintra/commit/{sha}", short or sha


def kind_cells(ctr):
    ctr = ctr or {}
    parts = []
    for k, cls in (("burn", "died"), ("stop", "timeout"), ("none", ""), ("poison", "died"), ("bleed", "died")):
        v = int(ctr.get(k, 0))
        if v:
            parts.append(pill(f"{k} {v}", cls))
    for k, v in ctr.items():
        if k not in ("burn", "stop", "none", "poison", "bleed"):
            parts.append(pill(f"{k} {v}"))
    return " ".join(parts) or "—"


def break_cells(db, exclusive=False):
    db = db or {}
    src = db.get("buckets") if exclusive and db.get("buckets") else db
    order = (
        ("contact_only", "contact", ""),
        ("burn_involved", "Burn", "died"),
        ("stop_involved", "Stop", "timeout"),
        ("lethal_poison_bleed", "lethal P/B", "died"),
        ("other_status", "other", ""),
    )
    parts = []
    for key, label, cls in order:
        v = int((src or {}).get(key, 0) or 0)
        if v:
            parts.append(pill(f"{label} {v}", cls))
    return " ".join(parts) or "—"


def oc_cell(oc):
    oc = oc or {}
    bits = []
    if oc.get("cleared"):
        bits.append(pill(f"cleared {oc['cleared']}", "ok"))
    if oc.get("died"):
        bits.append(pill(f"died {oc['died']}", "died"))
    if oc.get("timeout"):
        bits.append(pill(f"timeout {oc['timeout']}", "timeout"))
    if oc.get("left_room"):
        bits.append(pill(f"left {oc['left_room']}", "open"))
    return " ".join(bits) or "—"


def arrow(old, new, invert_good=False):
    try:
        o, n = int(old), int(new)
    except Exception:
        return esc(f"{old} → {new}")
    d = n - o
    if d == 0:
        cls = "muted"
        tail = " (0)"
    elif (d < 0) != invert_good:
        cls = "ok" if not invert_good else "bad"
        tail = f" ({d:+d})"
        # fewer deaths is good
        cls = "ok"
    else:
        cls = "bad"
        tail = f" ({d:+d})"
    return f"{o} → <span class=\"{cls}\">{n}{tail}</span>"


def chain_html(chain):
    chain = chain or {}
    return " ".join(
        pill(f"{k} {v}", "timeout" if ("dot" in k or "stop" in k) else "")
        for k, v in chain.items()
        if k and k != "none"
    ) or "—"


def matrix_table(block, kind):
    matrix = block.get("matrix") or {}
    heroes = []
    for recs in matrix.values():
        for h in recs:
            if h not in heroes:
                heroes.append(h)
    rows = []
    for skill, recs in matrix.items():
        cells = [f"<th>{esc(skill)}</th>"]
        for hero in heroes:
            rec = (recs or {}).get(hero) or {}
            n = rec.get("n", 0)
            c = rec.get("cleared", 0)
            d = rec.get("died", 0)
            t = rec.get("timeout", 0)
            label = []
            if c:
                label.append(f'<span class="ok">{c}/{n} clear</span>')
            if d:
                label.append(f'<span class="bad">{d}/{n} died</span>')
            if t:
                label.append(f'<span class="warn">{t}/{n} timeout</span>')
            extra = ""
            if kind == "boss" and rec.get("boss_hp_end"):
                ends = rec["boss_hp_end"]
                extra = f'<div class="muted">boss HP end {min(ends)}–{max(ends)}</div>'
            cells.append(f"<td>{'<br>'.join(label) or '—'}{extra}</td>")
        rows.append("<tr>" + "".join(cells) + "</tr>")
    head = "<tr><th>Skill</th>" + "".join(f"<th>{esc(h)}</th>" for h in heroes) + "</tr>"
    return f'<div class="table-wrap"><table class="runs-table"><thead>{head}</thead><tbody>{"".join(rows)}</tbody></table></div>'


def subset_row(name, b):
    b = b or {}
    return (
        f"<tr><th>{esc(name)}</th><td>{b.get('n', 0)}</td>"
        f"<td>{pct(b.get('died', 0), b.get('n', 0))}</td>"
        f"<td>{oc_cell(b.get('outcomes') or {})}</td>"
        f"<td>{kind_cells(b.get('death_kind'))}</td>"
        f"<td>{break_cells(b.get('death_break'))}</td>"
        f"<td>lands {b.get('lands_gt0', '—')} / harmful {b.get('harmful_gt0', '—')} / DoT {b.get('dot_gt0', '—')}</td></tr>"
    )


def kv_rows(mapping):
    rows = []
    for name, rec in (mapping or {}).items():
        rows.append(
            f"<tr><th>{esc(name)}</th><td>{rec.get('n', 0)}</td>"
            f"<td>{pct(rec.get('died', 0), rec.get('n', 0))}</td>"
            f"<td>{oc_cell(rec.get('outcomes') or {})}</td>"
            f"<td>{kind_cells(rec.get('death_kind'))}</td>"
            f"<td>{break_cells(rec.get('death_break'))}</td></tr>"
        )
    return "".join(rows)


def arena_section(diff, a):
    boss, entry = a.get("boss") or {}, a.get("entry") or {}
    bo, eo = boss.get("outcomes") or {}, entry.get("outcomes") or {}
    bdb = boss.get("death_break") or {}
    edb = entry.get("death_break") or {}
    return f"""
<section>
  <h2>Cinder Rex and stage-3 entry — {esc(diff.title())}</h2>
  <div class="stats">
    <div class="stat"><b>{pct(bo.get('cleared', 0), boss.get('n', 0))}</b><span>Cinder Rex clears</span></div>
    <div class="stat"><b>{pct(bo.get('died', 0), boss.get('n', 0))}</b><span>Cinder Rex deaths</span></div>
    <div class="stat"><b>{bdb.get('contact_only', bo.get('died', 0))}</b><span>Rex contact-only deaths</span></div>
    <div class="stat"><b>{pct(eo.get('died', 0), entry.get('n', 0))}</b><span>entry-foyer deaths</span></div>
  </div>
  <p class="meta">5 heroes × bot / skilled / average × 4 seeds. Cinder Rex starts at 240 HP.
     Harmful status lands in Rex fights: {boss.get('status_harmful', 0)}.
     Rex death break: {break_cells(bdb)}. Entry death break: {break_cells(edb)}.</p>
  <h3>Cinder Rex matrix</h3>
  {matrix_table(boss, "boss")}
  <h3>Stage-3 entry foyer</h3>
  {matrix_table(entry, "entry")}
</section>
"""


def rooms_section(diff, r):
    oc = r.get("outcomes") or {}
    all_row = {
        "n": r.get("n"),
        "died": r.get("deaths"),
        "outcomes": oc,
        "death_kind": r.get("death_kind"),
        "death_break": r.get("death_break"),
        "lands_gt0": "—",
        "harmful_gt0": "—",
        "dot_gt0": "—",
    }
    db = r.get("death_break") or {}
    extra = ""
    if r.get("cinder_maw") or r.get("cinder_kite"):
        extra = subset_row("Cinder Maw (14)", r.get("cinder_maw")) + subset_row(
            "Cinder Kite (25)", r.get("cinder_kite")
        )
    return f"""
<section>
  <h2>Stage-3 combat rooms — {esc(diff.title())}</h2>
  <div class="stats">
    <div class="stat"><b>{r.get('n', 0)}</b><span>fights</span></div>
    <div class="stat"><b>{pct(r.get('deaths', 0), r.get('n', 0))}</b><span>deaths</span></div>
    <div class="stat"><b>{db.get('contact_only', 0)}</b><span>contact-only</span></div>
    <div class="stat"><b>{db.get('burn_involved', (r.get('death_kind') or {}).get('burn', 0))}</b><span>Burn-involved</span></div>
    <div class="stat"><b>{db.get('stop_involved', (r.get('death_kind') or {}).get('stop', 0))}</b><span>Stop-involved</span></div>
    <div class="stat"><b>{db.get('lethal_poison_bleed', 0)}</b><span>lethal Poison/Bleed</span></div>
  </div>
  <p class="meta">Official <code>balance_rooms.py</code>: 80 fixtures per difficulty (Cinder Maw / Cinder Kite and Fold Star packs included)
     × 3 skills × 2 seeds = 480 fights. Death kind is the status at death.
     Burn carriers: Cinder Maw (14), Cinder Kite (25). Stop carrier: Fold Star (11).
     Contact-only = empty/none <code>death_kind</code> and no <code>death_chain</code>.
     Burn / Stop / lethal P/B flags may overlap.</p>
  <h3>By room type</h3>
  <div class="table-wrap"><table class="runs-table">
    <thead><tr><th>Subset</th><th>N</th><th>Deaths</th><th>Outcomes</th><th>Death kind</th><th>Death break</th><th>Status landings</th></tr></thead>
    <tbody>
      {subset_row("All rooms", all_row)}
      {subset_row("Cinder Maw / Kite (14, 25)", r.get("cinder"))}
      {extra}
      {subset_row("Fold Star / Stop (11)", r.get("fold_star"))}
      {subset_row("No 11 / 14 / 25", r.get("no_status_carriers"))}
    </tbody>
  </table></div>
  <h3>By skill</h3>
  <div class="table-wrap"><table class="runs-table">
    <thead><tr><th>Skill</th><th>N</th><th>Deaths</th><th>Outcomes</th><th>Death kind</th><th>Death break</th></tr></thead>
    <tbody>{kv_rows(r.get("by_skill"))}</tbody>
  </table></div>
  <h3>By hero</h3>
  <div class="table-wrap"><table class="runs-table">
    <thead><tr><th>Hero</th><th>N</th><th>Deaths</th><th>Outcomes</th><th>Death kind</th><th>Death break</th></tr></thead>
    <tbody>{kv_rows(r.get("by_hero"))}</tbody>
  </table></div>
  <p class="meta">Death chains: {chain_html(r.get("death_chain"))}.
     <code>dot_pinned_then_hit</code> is the #217 floor (DoT stops at 1 HP, then a hit finishes the run).
     <code>stop_then_hit</code> is a Stop proc followed by a hit while frozen.
     <code>dot_kill</code> is a lethal Poison or Bleed tick (new on #227; Burn still floors at 1 HP).</p>
</section>
"""


def csv_links(build, rec):
    csv = (rec or {}).get("csv") or {}
    if not csv:
        # published relative copies
        bits = [
            f'<a href="{esc(build)}/arena-s3-easy.csv"><code>arena-s3-easy.csv</code></a>',
            f'<a href="{esc(build)}/arena-s3-normal.csv"><code>arena-s3-normal.csv</code></a>',
            f'<a href="{esc(build)}/rooms-s3-easy.csv"><code>rooms-s3-easy.csv</code></a>',
            f'<a href="{esc(build)}/rooms-s3-normal.csv"><code>rooms-s3-normal.csv</code></a>',
        ]
        return " ".join(bits)
    return " ".join(
        f'<a href="{esc(build)}/{esc(Path(p).name)}"><code>{esc(Path(p).name)}</code></a>'
        for p in csv.values()
    )


def build_heading(build, rec, role):
    url, short = commit_url(build)
    sha = (rec or {}).get("rom_sha256") or ""
    return (
        f'<h2 id="{esc(short)}">{esc(role)}: <a href="{esc(url)}"><code>{esc(short)}</code></a></h2>'
        f'<p class="meta">ROM sha256 <code>{esc(sha[:16])}&hellip;</code>. Raw CSVs: {csv_links(short, rec)}.</p>'
    )


def build_detail(build, rec):
    arena, rooms = rec.get("arena") or {}, rec.get("rooms") or {}
    notes = "".join(f"<li>{esc(n)}</li>" for n in (rec.get("notes") or []))
    return f"""
<section>
  {build_heading(build, rec, rec.get("title") or "Build")}
  <ul>{notes}</ul>
  {arena_section("easy", arena.get("easy") or {})}
  {arena_section("normal", arena.get("normal") or {})}
  {rooms_section("easy", rooms.get("easy") or {})}
  {rooms_section("normal", rooms.get("normal") or {})}
</section>
"""


def compare_subset_row(row, name=None):
    name = name or row.get("subset") or ""
    labels = {
        "all": "All rooms",
        "cinder_maw_kite": "Cinder Maw / Kite (14, 25)",
        "cinder_maw": "Cinder Maw (14)",
        "cinder_kite": "Cinder Kite (25)",
        "fold_star": "Fold Star / Stop (11)",
        "no_status_carriers": "No 11 / 14 / 25",
    }
    label = labels.get(name, name)
    n = row.get("new_n") or row.get("old_n") or 0
    return (
        f"<tr><th>{esc(label)}</th><td>{n}</td>"
        f"<td>{arrow(row.get('old_died', 0), row.get('new_died', 0))}</td>"
        f"<td>{arrow(row.get('old_contact_only', 0), row.get('new_contact_only', 0))}</td>"
        f"<td>{arrow(row.get('old_burn_involved', 0), row.get('new_burn_involved', 0))}</td>"
        f"<td>{arrow(row.get('old_stop_involved', 0), row.get('new_stop_involved', 0))}</td>"
        f"<td>{arrow(row.get('old_lethal_poison_bleed', 0), row.get('new_lethal_poison_bleed', 0))}</td></tr>"
    )


def compare_arena_row(label, row):
    return (
        f"<tr><th>{esc(label)}</th><td>{row.get('new_n') or row.get('old_n') or 0}</td>"
        f"<td>{arrow(row.get('old_cleared', 0), row.get('new_cleared', 0), invert_good=True)}</td>"
        f"<td>{arrow(row.get('old_died', 0), row.get('new_died', 0))}</td>"
        f"<td>{arrow(row.get('old_contact_only', 0), row.get('new_contact_only', 0))}</td>"
        f"<td>{arrow(row.get('old_timeout', 0), row.get('new_timeout', 0))}</td>"
        f"<td>{esc(row.get('old_status_harmful', 0))} → {esc(row.get('new_status_harmful', 0))}</td></tr>"
    )


def fixture_rows(fixtures):
    if not fixtures:
        return "<tr><td colspan='6'>No fixture-level contact or death changes.</td></tr>"
    out = []
    for row in sorted(fixtures, key=lambda r: (-abs(int(r.get("d_contact_only") or 0)), r.get("subset") or "")):
        kinds = ",".join(row.get("enemy_kinds") or []) or "—"
        tags = []
        if row.get("cinder"):
            tags.append("cinder")
        if row.get("fold_star"):
            tags.append("fold")
        tag = f" <span class='muted'>({esc(' '.join(tags))})</span>" if tags else ""
        out.append(
            f"<tr><th>{esc(row.get('subset') or '')}{tag}</th>"
            f"<td><code>{esc(kinds)}</code></td>"
            f"<td>{arrow(row.get('old_died', 0), row.get('new_died', 0))}</td>"
            f"<td>{arrow(row.get('old_contact_only', 0), row.get('new_contact_only', 0))}</td>"
            f"<td>{arrow(row.get('old_burn_involved', 0), row.get('new_burn_involved', 0))}</td>"
            f"<td>{arrow(row.get('old_stop_involved', 0), row.get('new_stop_involved', 0))}</td></tr>"
        )
    return "".join(out)


def compare_diff_section(diff, block):
    rooms = block.get("rooms") or {}
    arena = block.get("arena") or {}
    subsets = rooms.get("subsets") or []
    changed = rooms.get("fixtures_changed") or []
    boss, entry = arena.get("boss") or {}, arena.get("entry") or {}
    return f"""
<section>
  <h2>Comparison — {esc(diff.title())}</h2>
  <h3>Rooms (480 fights)</h3>
  <div class="table-wrap"><table class="runs-table">
    <thead><tr><th>Subset</th><th>N</th><th>Deaths (old → new)</th><th>Contact-only</th><th>Burn-involved</th><th>Stop-involved</th><th>Lethal Poison/Bleed</th></tr></thead>
    <tbody>{"".join(compare_subset_row(s) for s in subsets)}</tbody>
  </table></div>
  <h3>Cinder Rex and entry foyer</h3>
  <div class="table-wrap"><table class="runs-table">
    <thead><tr><th>Slice</th><th>N</th><th>Clears (old → new)</th><th>Deaths</th><th>Contact-only</th><th>Timeouts</th><th>Harmful status lands</th></tr></thead>
    <tbody>
      {compare_arena_row("Cinder Rex (boss)", boss)}
      {compare_arena_row("Stage-3 entry foyer", entry)}
    </tbody>
  </table></div>
  <h3>Fixtures whose deaths or contact-only count changed</h3>
  <p class="meta">{len(changed)} of {len(rooms.get('fixtures_all') or [])} fixtures. Positive contact delta means more contact-only deaths on the new build.</p>
  <div class="table-wrap"><table class="runs-table">
    <thead><tr><th>Fixture</th><th>Enemy kinds</th><th>Deaths</th><th>Contact-only</th><th>Burn-involved</th><th>Stop-involved</th></tr></thead>
    <tbody>{fixture_rows(changed)}</tbody>
  </table></div>
</section>
"""


def wrap(title, body):
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{esc(title)}</title>
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


def single_page(summary):
    arena, rooms = summary.get("arena") or {}, summary.get("rooms") or {}
    build, sha = summary.get("build") or "", summary.get("rom_sha256") or ""
    url, short = commit_url(build)
    easy_b = (arena.get("easy") or {}).get("boss") or {}
    norm_b = (arena.get("normal") or {}).get("boss") or {}
    norm_r = rooms.get("normal") or {}
    notes = "".join(f"<li>{esc(n)}</li>" for n in (summary.get("notes") or []))
    ndb = norm_r.get("death_break") or {}
    body = f"""
<header>
  <p class="meta"><a href="../index.html">&larr; All runs</a></p>
  <h1>Stage 3 balance summary</h1>
  <p>Death breakdown and Cinder Rex matrix on
     <a href="{esc(url)}"><code>{esc(short)}</code></a>.
     Official human-skill bots (no deep RL). ROM sha256
     <code>{esc(sha[:16])}&hellip;</code>. Raw CSVs: {csv_links(short, summary)}. No ROM downloads.</p>
</header>
<main>
  <div class="stats">
    <div class="stat"><b>{pct((easy_b.get("outcomes") or {}).get("cleared", 0), easy_b.get("n", 0))}</b><span>Easy Cinder Rex clears</span></div>
    <div class="stat"><b>{pct((norm_b.get("outcomes") or {}).get("died", 0), norm_b.get("n", 0))}</b><span>Normal Cinder Rex deaths</span></div>
    <div class="stat"><b>{ndb.get("contact_only", 0)}</b><span>Normal contact-only room deaths</span></div>
    <div class="stat"><b>{ndb.get("burn_involved", (norm_r.get("death_kind") or {}).get("burn", 0))}</b><span>Normal Burn-involved</span></div>
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
    return wrap("Stage 3 balance summary — Quintra runs", body)


def compare_page(summary):
    base = summary.get("baseline_build") or ""
    cur = summary.get("current_build") or ""
    bu, bs = commit_url(base)
    cu, cs = commit_url(cur)
    builds = summary.get("builds") or {}
    diffs = summary.get("difficulties") or {}
    issue = summary.get("issue_228") or {}
    issue_notes = "".join(f"<li>{esc(n)}</li>" for n in (issue.get("notes") or []))
    # headline stats from normal rooms + rex
    norm = (diffs.get("normal") or {}).get("rooms") or {}
    all_n = next((s for s in (norm.get("subsets") or []) if s.get("subset") == "all"), {})
    rex_n = ((diffs.get("normal") or {}).get("arena") or {}).get("boss") or {}
    rex_e = ((diffs.get("easy") or {}).get("arena") or {}).get("boss") or {}
    body = f"""
<header>
  <p class="meta"><a href="../index.html">&larr; All runs</a></p>
  <h1>Stage 3 balance comparison</h1>
  <p>Official Player sweep re-baselined on
     <a href="{esc(cu)}"><code>{esc(cs)}</code></a>
     (PR #227: Maw/Kite Burn proc trimmed, Poison/Bleed lethal, Burn still floors at 1 HP).
     Baseline kept:
     <a href="{esc(bu)}"><code>{esc(bs)}</code></a>
     (#219 Confusion; also the commit immediately before #221).
     Same method both times: Cinder Rex <code>balance_arena.py</code> (5 heroes × 3 skills × 4 seeds, Easy + Normal)
     and stage-3 <code>balance_rooms.py</code> (480 fights each difficulty). No ROM downloads.</p>
</header>
<main>
  <div class="stats">
    <div class="stat"><b>{arrow(all_n.get('old_died', 0), all_n.get('new_died', 0))}</b><span>Normal room deaths</span></div>
    <div class="stat"><b>{arrow(all_n.get('old_contact_only', 0), all_n.get('new_contact_only', 0))}</b><span>Normal contact-only</span></div>
    <div class="stat"><b>{arrow(rex_e.get('old_cleared', 0), rex_e.get('new_cleared', 0), invert_good=True)}</b><span>Easy Cinder Rex clears</span></div>
    <div class="stat"><b>{arrow(rex_n.get('old_died', 0), rex_n.get('new_died', 0))}</b><span>Normal Cinder Rex deaths</span></div>
  </div>
  {compare_diff_section("easy", diffs.get("easy") or {})}
  {compare_diff_section("normal", diffs.get("normal") or {})}
  <section>
    <h2>Issue #228 — did #221 raise contact deaths?</h2>
    <p class="meta"><a href="https://github.com/struktured-labs/quintra/issues/228">quintra#228</a>.
       {esc(issue.get("title") or "")}</p>
    <ul>{issue_notes or "<li>Verdict will be filled from the comparison CSVs.</li>"}</ul>
  </section>
  {build_detail(cur, builds.get(cur) or {})}
  {build_detail(base, builds.get(base) or {})}
  <section>
    <h2>How to read this</h2>
    <ul>
      <li>Old = <a href="{esc(bu)}"><code>{esc(bs)}</code></a>. New = <a href="{esc(cu)}"><code>{esc(cs)}</code></a>.</li>
      <li>Contact-only deaths have empty/none <code>death_kind</code> and no <code>death_chain</code>. Burn-involved, Stop-involved, and lethal Poison/Bleed are overlapping flags.</li>
      <li><code>dot_pinned_then_hit</code> is the #217 Burn floor (stops at 1 HP, then a hit). <code>dot_kill</code> is a lethal Poison/Bleed tick added in #227. <code>stop_then_hit</code> is a Stop proc followed by a hit while frozen.</li>
      <li>Source: <a href="summary.json"><code>summary.json</code></a>. Generated from official harness CSVs; the 684bac5c baseline is kept in full below the comparison.</li>
    </ul>
  </section>
</main>
"""
    return wrap("Stage 3 balance comparison — Quintra runs", body)


def page(summary):
    schema = summary.get("schema") or ""
    if schema == "quintra-balance-compare-v1" or (summary.get("builds") and summary.get("difficulties")):
        return compare_page(summary)
    return single_page(summary)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--summary", type=Path, default=Path("balance/summary.json"))
    ap.add_argument("--out", type=Path, default=Path("balance/index.html"))
    args = ap.parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(page(json.loads(args.summary.read_text())))
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
