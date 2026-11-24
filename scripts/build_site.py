#!/usr/bin/env python3
"""Build the static quintra-runs site from recorded run directories.

Copies only approved media (json, png, gif, mp4, webm, md, common images).
Refuses ROM / SRAM / emulator-state / password files, and videos >= 50 MB.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

ALLOWED_EXT = {
    ".json", ".png", ".gif", ".mp4", ".webm",
    ".jpg", ".jpeg", ".webp", ".svg", ".md",
}
REFUSED_EXT = {
    ".gbc", ".gb", ".gba", ".gbs", ".sgb",
    ".sav", ".srm", ".ram", ".rtc",
    ".noi", ".ihx", ".map", ".sym",
    ".pyboy", ".state", ".sn1", ".sn2", ".ss0", ".ss1",
}
SECRET_NAME_RE = re.compile(
    r"(password|passwd|secret|token|credential|itch[-_]?pw|\.env$|id_rsa)",
    re.I,
)
MAX_VIDEO_BYTES = 50 * 1024 * 1024
ROOT_DEFAULT = Path(__file__).resolve().parent.parent
BOX_ARCHIVE = Path("/workspace/quintra-runs")
QUINTRA_COMMIT_URL = "https://github.com/struktured-labs/quintra/commit/{sha}"


def html_escape(text) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def pill(text: str, kind: str = "") -> str:
    if not text:
        return ""
    cls = f"pill {kind}".strip()
    return f'<span class="{cls}">{html_escape(text)}</span>'


def outcome_class(outcome: str) -> str:
    return {
        "won": "ok",
        "cleared": "ok",
        "died": "died",
        "crash": "crash",
        "timeout": "timeout",
        "open": "open",
    }.get((outcome or "").lower(), "")


def fmt_dt(value: str | None) -> str:
    if not value:
        return "—"
    try:
        dt = datetime.fromisoformat(value)
        # Timestamps are recorded in America/New_York.
        return dt.strftime("%b %-d, %Y %-I:%M %p ET")
    except ValueError:
        return str(value)


def fmt_seconds(value) -> str:
    if value is None or value == "":
        return "—"
    try:
        total = float(value)
    except (TypeError, ValueError):
        return str(value)
    secs = int(round(total))
    hours, rem = divmod(secs, 3600)
    minutes, rem = divmod(rem, 60)
    if hours:
        clock = f"{hours}h {minutes:02d}m {rem:02d}s"
    elif minutes:
        clock = f"{minutes}m {rem:02d}s"
    else:
        clock = f"{rem}s"
    if not float(total).is_integer():
        return f"{clock} ({total}s)"
    return clock if secs < 60 else f"{clock} ({secs}s)"


def furthest(run: dict) -> str:
    end = run.get("end") or {}
    stage = end.get("stage")
    room = end.get("room")
    bosses = end.get("bosses") or 0
    if stage is None:
        stages = run.get("stages") or []
        if stages:
            last = max(stages, key=lambda s: s.get("stage") or 0)
            stage = last.get("stage")
            rooms = last.get("rooms") or []
            if room is None and rooms:
                room = rooms[-1]
            if not bosses:
                bosses = last.get("boss_cleared") or 0
    parts: list[str] = []
    if stage is not None:
        parts.append(f"stage {stage}")
    if room is not None:
        parts.append(f"room {room}")
    if bosses:
        noun = "boss" if bosses == 1 else "bosses"
        parts.append(f"{bosses} {noun}")
    return ", ".join(parts) or "—"


def thumb_for(run: dict) -> str:
    shots = run.get("screenshots") or []
    preferred = []
    others = []
    for shot in shots:
        if shot.get("blank") or not shot.get("file"):
            continue
        name = Path(shot["file"]).name
        if name.startswith("09-") or name.startswith("07-") or name.startswith("05-"):
            preferred.append(shot["file"])
        else:
            others.append(shot["file"])
    return (preferred or others or [""])[-1] if (preferred or others) else ""


def is_refused(path: Path) -> bool:
    ext = path.suffix.lower()
    name = path.name
    if ext in REFUSED_EXT or name.startswith(".itch"):
        return True
    if SECRET_NAME_RE.search(name):
        return True
    return False


def load_runs(sources: list[Path]) -> list[dict]:
    by_id: dict[str, dict] = {}
    for src in sources:
        if not src.exists():
            continue
        for path in sorted(src.glob("*/run.json")):
            parent = path.parent
            if parent.name.startswith("_"):
                continue
            data = json.loads(path.read_text())
            run_id = data.get("id") or parent.name
            data["id"] = run_id
            data["_src"] = parent
            by_id[run_id] = data
    runs = list(by_id.values())
    runs.sort(key=lambda r: r.get("started") or r.get("id") or "", reverse=True)
    return runs


def copy_media(src: Path, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    for item in src.rglob("*"):
        if not item.is_file():
            continue
        ext = item.suffix.lower()
        if is_refused(item):
            raise SystemExit(f"refusing to copy {item}")
        if ext not in ALLOWED_EXT:
            continue
        if ext in {".mp4", ".webm"} and item.stat().st_size >= MAX_VIDEO_BYTES:
            raise SystemExit(
                f"video exceeds 50 MB ({item.stat().st_size} bytes): {item}"
            )
        rel = item.relative_to(src)
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(item, target)


def md_inline(text: str) -> str:
    s = html_escape(text)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", s)
    return s


def md_to_html(text: str) -> str:
    lines = text.splitlines()
    out: list[str] = []
    in_list = False
    skipped_title = False

    def close_list() -> None:
        nonlocal in_list
        if in_list:
            out.append("</ul>")
            in_list = False

    for line in lines:
        if line.startswith("# ") and not skipped_title:
            skipped_title = True
            continue
        if line.startswith("### "):
            close_list()
            out.append(f"<h3>{md_inline(line[4:])}</h3>")
        elif line.startswith("## "):
            close_list()
            out.append(f"<h3>{md_inline(line[3:])}</h3>")
        elif line.startswith("# "):
            close_list()
            out.append(f"<h3>{md_inline(line[2:])}</h3>")
        elif line.startswith("- ") or line.startswith("* "):
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append(f"<li>{md_inline(line[2:])}</li>")
        elif line.strip() == "":
            close_list()
        else:
            close_list()
            out.append(f"<p>{md_inline(line)}</p>")
    close_list()
    return "\n".join(out)


def page_shell(title: str, body: str, root_prefix: str = "") -> str:
    css = f"{root_prefix}styles.css"
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html_escape(title)}</title>
  <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@500;600&family=IBM+Plex+Sans:wght@400;600&display=swap">
  <link rel="stylesheet" href="{css}">
</head>
<body>
{body}
<footer>
  Quintra playtest log. Screenshots and video only — no ROM downloads.
</footer>
</body>
</html>
"""


def index_html(runs: list[dict]) -> str:
    deaths_total = sum(len(r.get("deaths") or []) for r in runs)
    heroes = sorted({r.get("hero") or "?" for r in runs})
    best = None
    for run in runs:
        end = run.get("end") or {}
        key = (end.get("stage") or 0, end.get("bosses") or 0, end.get("room") or 0)
        if best is None or key > best[0]:
            best = (key, run)
    best_label = "—"
    if best:
        run = best[1]
        best_label = f"{furthest(run)} ({run.get('hero')})"

    rows = []
    for run in runs:
        shot = thumb_for(run)
        thumb = f'runs/{run["id"]}/{shot}' if shot else ""
        img = (
            f'<img class="thumb" src="{html_escape(thumb)}" alt="">'
            if thumb
            else ""
        )
        sha = run.get("build_sha") or ""
        sha_short = sha[:8] if sha else "—"
        if sha:
            href = QUINTRA_COMMIT_URL.format(sha=sha)
            sha_html = f'<a href="{html_escape(href)}"><code>{html_escape(sha_short)}</code></a>'
        else:
            sha_html = f"<code>{html_escape(sha_short)}</code>"
        policy = run.get("player_policy") or ""
        policy_html = (
            f'<div class="muted">{html_escape(policy)}</div>' if policy else ""
        )
        rid = html_escape(run["id"])
        rows.append(
            "<tr>"
            f"<td>{img}</td>"
            f'<td><a class="id" href="runs/{rid}/">{rid}</a></td>'
            f"<td>{html_escape(fmt_dt(run.get('started')))}</td>"
            f"<td>{sha_html}</td>"
            f"<td>{html_escape(run.get('hero', '—'))}</td>"
            f"<td>{html_escape(run.get('player_type', '—'))}{policy_html}</td>"
            f"<td>{html_escape(run.get('difficulty', '—'))}</td>"
            f"<td>{pill(run.get('outcome', '—'), outcome_class(run.get('outcome', '')))}</td>"
            f"<td>{html_escape(furthest(run))}</td>"
            f"<td>{len(run.get('deaths') or [])}</td>"
            "</tr>"
        )

    body = f"""
<header>
  <h1>Quintra runs</h1>
  <p>Recorded playtests for the Game Boy Color roguelike. Machine and human-style
     sessions, with per-stage times and death causes. No ROMs.</p>
  <p class="meta"><a href="balance/">Stage 3 balance summary</a> — Cinder Rex
     matrix and Stop/Burn room deaths on current main.</p>
</header>
<main>
  <div class="stats">
    <div class="stat"><b>{len(runs)}</b><span>recorded run{"s" if len(runs) != 1 else ""}</span></div>
    <div class="stat"><b>{html_escape(", ".join(heroes) or "—")}</b><span>heroes tried</span></div>
    <div class="stat"><b>{html_escape(best_label)}</b><span>furthest progress</span></div>
    <div class="stat"><b>{deaths_total}</b><span>deaths logged</span></div>
  </div>
  <div class="table-wrap">
    <table class="runs-table">
      <thead>
        <tr>
          <th></th>
          <th>Run id</th>
          <th>Date</th>
          <th>Build</th>
          <th>Hero</th>
          <th>Player type</th>
          <th>Difficulty</th>
          <th>Outcome</th>
          <th>Furthest progress</th>
          <th>Deaths</th>
        </tr>
      </thead>
      <tbody>
        {"".join(rows) or '<tr><td colspan="10">No runs yet.</td></tr>'}
      </tbody>
    </table>
  </div>
</main>
"""
    return page_shell("Quintra runs", body)


def run_html(run: dict) -> str:
    timings = run.get("timings") or {}
    end = run.get("end") or {}
    sha = run.get("build_sha") or ""
    pills = " ".join(
        filter(
            None,
            [
                pill(run.get("hero", "?")),
                pill(run.get("difficulty", "?")),
                pill(run.get("player_type", "?")),
                pill(run.get("player_policy") or ""),
                pill(run.get("outcome", "?"), outcome_class(run.get("outcome", ""))),
            ],
        )
    )

    sha_cell = sha
    if sha:
        href = QUINTRA_COMMIT_URL.format(sha=sha)
        sha_cell_html = (
            f'<a href="{html_escape(href)}"><code>{html_escape(sha)}</code></a>'
        )
    else:
        sha_cell_html = "—"

    emu = run.get("emulator")
    if isinstance(emu, dict):
        emu_s = "{name} {version} (window={window}, cgb={cgb})".format(**emu)
    else:
        emu_s = emu

    end_state = (
        f"screen={end.get('screen_name')} room={end.get('room')} "
        f"hp={end.get('hp')}/{end.get('hp_max')} score={end.get('score')} "
        f"coins={end.get('coins')}"
    )

    kv_rows = [
        ("Run id", f"<code>{html_escape(run.get('id'))}</code>"),
        ("Build SHA", sha_cell_html),
        (
            "ROM sha256",
            f"<code>{html_escape(run.get('rom_sha256'))}</code>"
            if run.get("rom_sha256")
            else None,
        ),
        ("Emulator", f"<code>{html_escape(emu_s)}</code>" if emu_s else None),
        ("Seed", f"<code>{html_escape(run.get('seed'))}</code>" if run.get("seed") is not None else None),
        ("Started", html_escape(fmt_dt(run.get("started")))),
        ("Ended", html_escape(fmt_dt(run.get("ended")))),
        ("Play time", html_escape(fmt_seconds(timings.get("play_s")))),
        ("Wall time", html_escape(fmt_seconds(timings.get("wall_s")))),
        (
            "Emulated frames",
            html_escape(timings.get("emulated_frames"))
            if timings.get("emulated_frames") is not None
            else None,
        ),
        ("Outcome", pill(run.get("outcome", "—"), outcome_class(run.get("outcome", "")))),
        ("Furthest progress", html_escape(furthest(run))),
        ("End state", f"<code>{html_escape(end_state)}</code>"),
    ]
    kv_html = "\n".join(
        f"<dt>{html_escape(k)}</dt><dd>{v}</dd>" for k, v in kv_rows if v not in (None, "")
    )

    stage_rows = []
    for s in run.get("stages") or []:
        status = ", ".join(f"{k}:{v}" for k, v in (s.get("status") or {}).items()) or "—"
        causes = ", ".join(s.get("death_causes") or []) or "—"
        rooms = s.get("rooms")
        if isinstance(rooms, list):
            rooms_s = ", ".join(str(x) for x in rooms)
        else:
            rooms_s = str(rooms) if rooms is not None else "—"
        stage_rows.append(
            "<tr>"
            f"<td>{html_escape(s.get('stage'))}</td>"
            f"<td>{html_escape(fmt_seconds(s.get('play_s')))}</td>"
            f"<td>{html_escape(s.get('room_count'))} ({html_escape(rooms_s)})</td>"
            f"<td>{html_escape(s.get('dmg'))} / {html_escape(s.get('hits'))} hits</td>"
            f"<td>{html_escape(s.get('deaths'))} ({html_escape(causes)})</td>"
            f"<td>seen={html_escape(s.get('boss_seen'))} cleared={html_escape(s.get('boss_cleared'))}"
            f" ({html_escape(fmt_seconds(s.get('boss_s')))})</td>"
            f"<td>{html_escape(status)}</td>"
            f"<td>{pill(s.get('outcome', ''), outcome_class(s.get('outcome', '')))}</td>"
            "</tr>"
        )
    stages_table = (
        """
<table>
  <thead><tr><th>Stage</th><th>Play</th><th>Rooms</th><th>Damage</th><th>Deaths</th><th>Boss</th><th>Status</th><th>Outcome</th></tr></thead>
  <tbody>
"""
        + "\n".join(stage_rows)
        + "</tbody></table>"
        if stage_rows
        else "<p class='meta'>No stage rows.</p>"
    )

    death_rows = []
    for dth in run.get("deaths") or []:
        death_rows.append(
            "<tr>"
            f"<td>{html_escape(dth.get('stage'))}</td>"
            f"<td>{html_escape(dth.get('room'))}</td>"
            f"<td>{html_escape(dth.get('cause'))}</td>"
            f"<td>{html_escape(dth.get('status') or '—')} ({html_escape(dth.get('status_age_s'))}s)</td>"
            f"<td>boss={html_escape(dth.get('in_boss'))}</td>"
            f"<td>t={html_escape(fmt_seconds(dth.get('play_s')))} frame={html_escape(dth.get('frame'))}</td>"
            "</tr>"
        )
    deaths_html = (
        """
<table>
  <thead><tr><th>Stage</th><th>Room</th><th>Cause</th><th>Status</th><th>Boss</th><th>When</th></tr></thead>
  <tbody>
"""
        + "\n".join(death_rows)
        + "</tbody></table>"
        if death_rows
        else "<p class='meta'>No deaths this run.</p>"
    )

    figures = []
    for shot in run.get("screenshots") or []:
        note = shot.get("note") or ""
        blank = " (blank/fade)" if shot.get("blank") else ""
        figures.append(
            f'<figure><img src="{html_escape(shot["file"])}" alt="{html_escape(note)}">'
            f'<figcaption>{html_escape(Path(shot["file"]).name)} — {html_escape(note)}{blank}'
            f' · {html_escape(shot.get("colors"))} colors</figcaption></figure>'
        )

    media = []
    if run.get("gif"):
        media.append(
            f'<div class="media"><h2>Opening GIF</h2>'
            f'<img src="{html_escape(run["gif"])}" alt="opening gif"></div>'
        )
    if run.get("video"):
        media.append(
            f'<div class="media"><h2>Gameplay</h2>'
            f'<video controls preload="metadata" src="{html_escape(run["video"])}"></video></div>'
        )

    downloads = ['<a href="run.json">run.json</a>']
    if run.get("telemetry"):
        downloads.append(f'<a href="{html_escape(run["telemetry"])}">telemetry.json</a>')
    if run.get("commentary"):
        downloads.append(f'<a href="{html_escape(run["commentary"])}">commentary.md</a>')
    if run.get("video"):
        downloads.append(f'<a href="{html_escape(run["video"])}">gameplay.mp4</a>')
    if run.get("gif"):
        downloads.append(f'<a href="{html_escape(run["gif"])}">opening GIF</a>')
    downloads_html = '<p class="downloads">' + " · ".join(downloads) + "</p>"

    commentary_html = ""
    src = run.get("_src")
    cname = run.get("commentary") or "commentary.md"
    cpath = (src / cname) if src else None
    if cpath and cpath.exists():
        commentary_html = (
            "<h2>Commentary</h2>\n"
            f'<div class="commentary">{md_to_html(cpath.read_text())}</div>'
        )

    notes = "".join(f"<li>{html_escape(n)}</li>" for n in (run.get("notes") or [])) or "<li>None.</li>"
    bugs = "".join(f"<li>{html_escape(n)}</li>" for n in (run.get("bugs") or [])) or "<li>None recorded.</li>"

    body = f"""
<header>
  <p class="meta"><a href="../../index.html">← All runs</a></p>
  <h1>{html_escape(run.get("id"))}</h1>
  <div class="pills">{pills}</div>
  <p class="meta">{html_escape(run.get("hero"))} · {html_escape(run.get("difficulty"))} ·
     build {html_escape((sha or "")[:8])} · {html_escape(furthest(run))}</p>
</header>
<main>
  <p class="notice">This page never hosts the cartridge or a ROM download.</p>
  <h2>Summary</h2>
  <dl class="kv">{kv_html}</dl>
  <h2>Downloads</h2>
  {downloads_html}
  <h2>Stages</h2>
  {stages_table}
  <h2>Deaths</h2>
  {deaths_html}
  {commentary_html}
  {"".join(media)}
  <h2>Screenshots</h2>
  <div class="gallery">{"".join(figures)}</div>
  <h2>Notes</h2>
  <ul>{notes}</ul>
  <h2>Suspected bugs</h2>
  <ul>{bugs}</ul>
</main>
"""
    return page_shell(f"{run.get('id')} · Quintra runs", body, root_prefix="../../")


SCAN_SKIP_DIRS = {".git", "__pycache__", ".venv", "node_modules"}
SCAN_ALLOWED_EXT = ALLOWED_EXT | {".html", ".css", ".txt", ".py", ".yml", ".yaml", ".toml", ".in", "", ".csv"}  # balance harness CSVs are numeric fight logs, not ROMs

# Credential-shaped values only — documentation may mention the words "itch password".
SECRET_CONTENT_RE = re.compile(
    r"("
    r"ITCH_PASSWORD\s*[=:]\s*\S+"
    r"|ghp_[A-Za-z0-9]{20,}"
    r"|gho_[A-Za-z0-9]{20,}"
    r"|github_pat_[A-Za-z0-9_]{20,}"
    r"|AKIA[0-9A-Z]{16}"
    r")"
)


def iter_files(root: Path):
    for item in root.rglob("*"):
        if not item.is_file():
            continue
        if any(part in SCAN_SKIP_DIRS for part in item.parts):
            continue
        yield item


def scan_tree(root: Path) -> list[str]:
    problems: list[str] = []
    for item in iter_files(root):
        try:
            rel = item.relative_to(root)
        except ValueError:
            rel = item
        if is_refused(item):
            problems.append(f"forbidden file: {rel}")
            continue
        if item.suffix.lower() in {".mp4", ".webm"} and item.stat().st_size >= MAX_VIDEO_BYTES:
            problems.append(f"video >= 50 MB ({item.stat().st_size} bytes): {rel}")
        if item.suffix.lower() not in SCAN_ALLOWED_EXT:
            problems.append(f"unexpected file type: {rel}")
    for item in iter_files(root):
        if item.suffix.lower() not in {".html", ".css", ".md", ".json", ".txt", ".py", ".yml", ".yaml", ".toml"}:
            continue
        try:
            text = item.read_text(errors="replace")
        except OSError:
            continue
        if SECRET_CONTENT_RE.search(text):
            problems.append(f"possible secret in {item.relative_to(root)}")
    return problems


def default_sources(out: Path, explicit: list[Path]) -> list[Path]:
    sources = list(explicit)
    if not sources:
        if BOX_ARCHIVE.exists():
            sources.append(BOX_ARCHIVE)
        if (out / "runs").exists():
            sources.append(out / "runs")
    return sources


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--src", type=Path, action="append", default=None,
                        help="Directory of run folders (repeatable).")
    parser.add_argument("--out", type=Path, default=ROOT_DEFAULT)
    parser.add_argument("--scan-only", action="store_true",
                        help="Only scan --out for forbidden files.")
    args = parser.parse_args()
    out = args.out.resolve()

    if args.scan_only:
        problems = scan_tree(out)
        if problems:
            print("scan failed:", file=sys.stderr)
            for p in problems:
                print(f"  {p}", file=sys.stderr)
            return 1
        print(f"scan clean: {out}")
        return 0

    sources = default_sources(out, args.src or [])
    if not sources:
        raise SystemExit("no --src given and no default run archive found")
    runs = load_runs(sources)
    out.mkdir(parents=True, exist_ok=True)

    # Rebuild run pages from source folders. Keep styles/README/tools intact.
    catalog = []
    seen_ids = set()
    for run in runs:
        dest = out / "runs" / run["id"]
        if dest.exists():
            # If the source is already the destination, just rewrite HTML.
            src = run["_src"].resolve()
            if src != dest.resolve():
                shutil.rmtree(dest)
                copy_media(run["_src"], dest)
        else:
            copy_media(run["_src"], dest)
        (dest / "index.html").write_text(run_html(run))
        seen_ids.add(run["id"])
        catalog.append(
            {k: v for k, v in run.items() if not k.startswith("_") and k != "screenshots"}
            | {
                "id": run["id"],
                "screenshots": run.get("screenshots"),
                "furthest": furthest(run),
                "href": f"runs/{run['id']}/",
            }
        )

    (out / "runs").mkdir(exist_ok=True)
    (out / "runs" / "index.json").write_text(json.dumps(catalog, indent=2) + "\n")
    (out / "index.html").write_text(index_html(runs))
    summary = out / "balance" / "summary.json"
    if summary.exists():
        builder = Path(__file__).resolve().parent / "build_balance_page.py"
        if builder.exists():
            import subprocess
            subprocess.check_call([
                sys.executable, str(builder),
                "--summary", str(summary),
                "--out", str(out / "balance" / "index.html"),
            ])
    (out / ".nojekyll").touch()

    problems = scan_tree(out)
    if problems:
        print("build wrote files but the safety scan failed:", file=sys.stderr)
        for p in problems:
            print(f"  {p}", file=sys.stderr)
        return 1
    print(f"wrote {len(runs)} run(s) to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
