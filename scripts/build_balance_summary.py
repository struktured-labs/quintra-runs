#!/usr/bin/env python3
"""Build a JSON summary of stage-3 arena + room sweeps for the run-log site.

Supports a single-build (v1-compatible) summary plus a comparison document
that keeps a baseline (684bac5c) next to a newer build and breaks deaths into
contact-only, Burn-involved, Stop-involved, and lethal Poison/Bleed.
"""
from __future__ import annotations

import argparse
import collections
import csv
import json
from pathlib import Path

HEROES = ("wolfkin", "sauran", "corvin", "picsean", "vespine")
SKILLS = ("bot", "skilled", "average")
SCHEMA_BUILD = "quintra-balance-summary-v1"
SCHEMA_COMPARE = "quintra-balance-compare-v1"


def rows(path):
    p = Path(path)
    if not p.exists():
        return []
    return list(csv.DictReader(p.open()))


def ctr(xs):
    return dict(collections.Counter(xs))


def ni(x, d=0):
    try:
        return int(x)
    except Exception:
        return d


def has_kind(r, kid):
    return str(kid) in str(r.get("enemy_kinds") or "").replace(",", " ").split()


def norm(s):
    return (s or "").strip().lower()


def chain_tokens(s):
    raw = (s or "").strip()
    if not raw or raw.lower() == "none":
        return []
    return [t for t in raw.replace(",", "+").split("+") if t and t.lower() != "none"]


def room_death_flags(r):
    kind = norm(r.get("death_kind")) or "none"
    tokens = chain_tokens(r.get("death_chain"))
    lethal_pb = kind in {"poison", "bleed"} or any(
        t == "dot_kill" or t.startswith("dot_kill") for t in tokens
    )
    burn = kind == "burn" or any("burn" in t for t in tokens)
    stop = kind == "stop" or any("stop" in t for t in tokens)
    contact_only = (
        kind in {"", "none"}
        and not tokens
        and not lethal_pb
        and not burn
        and not stop
    )
    if lethal_pb:
        bucket = "lethal_poison_bleed"
    elif burn:
        bucket = "burn_involved"
    elif stop:
        bucket = "stop_involved"
    elif tokens or kind not in {"", "none"}:
        bucket = "other_status"
    else:
        bucket = "contact_only"
    return {
        "kind": kind,
        "chain": "+".join(tokens) if tokens else "none",
        "tokens": tokens,
        "contact_only": contact_only,
        "burn_involved": burn,
        "stop_involved": stop,
        "lethal_poison_bleed": lethal_pb,
        "bucket": bucket,
    }


def arena_death_flags(r):
    kind = norm(r.get("death_status_kind")) or "none"
    active = norm(r.get("death_status_active")) or "none"
    lethal_pb = kind in {"poison", "bleed"} or active in {"poison", "bleed"}
    burn = kind == "burn" or active == "burn"
    stop = kind == "stop" or active == "stop"
    contact_only = kind in {"", "none"} and active in {"", "none"} and not (lethal_pb or burn or stop)
    if lethal_pb:
        bucket = "lethal_poison_bleed"
    elif burn:
        bucket = "burn_involved"
    elif stop:
        bucket = "stop_involved"
    elif kind not in {"", "none"} or active not in {"", "none"}:
        bucket = "other_status"
    else:
        bucket = "contact_only"
    return {
        "kind": kind,
        "active": active,
        "contact_only": contact_only,
        "burn_involved": burn,
        "stop_involved": stop,
        "lethal_poison_bleed": lethal_pb,
        "bucket": bucket,
    }


def death_break(deaths, flags_fn):
    contact = burn = stop = lethal = other = 0
    buckets = collections.Counter()
    kinds = collections.Counter()
    chains = collections.Counter()
    overlap_burn_stop = 0
    overlap_pb_other = 0
    for r in deaths:
        f = flags_fn(r)
        if f["contact_only"]:
            contact += 1
        if f["burn_involved"]:
            burn += 1
        if f["stop_involved"]:
            stop += 1
        if f["lethal_poison_bleed"]:
            lethal += 1
        if f["bucket"] == "other_status":
            other += 1
        if f["burn_involved"] and f["stop_involved"]:
            overlap_burn_stop += 1
        if f["lethal_poison_bleed"] and (f["burn_involved"] or f["stop_involved"]):
            overlap_pb_other += 1
        buckets[f["bucket"]] += 1
        kinds[f["kind"]] += 1
        if "chain" in f:
            chains[f["chain"]] += 1
    out = {
        "contact_only": contact,
        "burn_involved": burn,
        "stop_involved": stop,
        "lethal_poison_bleed": lethal,
        "other_status": other,
        "buckets": dict(buckets),
        "death_kind": dict(kinds),
        "overlap_burn_stop": overlap_burn_stop,
        "overlap_lethal_pb_with_burn_or_stop": overlap_pb_other,
    }
    if chains:
        out["death_chain"] = dict(chains)
    return out


def analyze_arena(path, difficulty):
    rs = rows(path)
    out = {"difficulty": difficulty, "n": len(rs), "boss": {}, "entry": {}}
    for kind in ("boss", "entry"):
        ks = [r for r in rs if r.get("kind") == kind]
        deaths = [r for r in ks if r.get("outcome") == "died"]
        block = {
            "n": len(ks),
            "outcomes": ctr(r["outcome"] for r in ks),
            "deaths": len(deaths),
            "death_status_active": ctr(r.get("death_status_active") or "none" for r in deaths),
            "death_status_kind": ctr(r.get("death_status_kind") or "none" for r in deaths),
            "death_break": death_break(deaths, arena_death_flags),
            "status_lands": sum(ni(r.get("status_lands")) for r in ks),
            "status_harmful": sum(ni(r.get("status_harmful")) for r in ks),
            "matrix": {},
        }
        kinds = collections.Counter()
        for r in ks:
            for part in (r.get("status_kinds") or "").split(";"):
                if part and ":" in part:
                    k, v = part.split(":", 1)
                    kinds[k] += ni(v)
        block["status_kinds"] = dict(kinds)
        for skill in SKILLS:
            block["matrix"][skill] = {}
            for hero in HEROES:
                hs = [r for r in ks if r["skill"] == skill and r["hero"] == hero]
                if not hs:
                    continue
                oc = ctr(r["outcome"] for r in hs)
                rec = {
                    "n": len(hs),
                    "outcomes": oc,
                    "cleared": oc.get("cleared", 0),
                    "died": oc.get("died", 0),
                    "timeout": oc.get("timeout", 0),
                    "frames": [ni(r["frames"]) for r in hs],
                }
                if kind == "boss":
                    rec["boss_hp_end"] = [ni(r["boss_hp_end"]) for r in hs]
                    rec["boss_hp_start"] = [ni(r["boss_hp_start"]) for r in hs]
                block["matrix"][skill][hero] = rec
        out[kind] = block
    return out


def room_subset(xs):
    d = [r for r in xs if r.get("outcome") == "died"]
    return {
        "n": len(xs),
        "outcomes": ctr(r["outcome"] for r in xs),
        "died": len(d),
        "death_kind": ctr(r.get("death_kind") or "none" for r in d),
        "death_chain": ctr(r.get("death_chain") or "none" for r in d),
        "death_break": death_break(d, room_death_flags),
        "lands_gt0": sum(1 for r in xs if ni(r.get("lands")) > 0),
        "harmful_gt0": sum(1 for r in xs if ni(r.get("harmful")) > 0),
        "dot_gt0": sum(1 for r in xs if ni(r.get("dot_dmg")) > 0),
    }


def analyze_rooms(path, difficulty):
    rs = rows(path)
    deaths = [r for r in rs if r.get("outcome") == "died"]
    out = {
        "difficulty": difficulty,
        "n": len(rs),
        "outcomes": ctr(r["outcome"] for r in rs),
        "deaths": len(deaths),
        "death_kind": ctr(r.get("death_kind") or "none" for r in deaths),
        "death_chain": ctr(r.get("death_chain") or "none" for r in deaths),
        "death_break": death_break(deaths, room_death_flags),
        "cinder": room_subset(
            [r for r in rs if has_kind(r, 14) or has_kind(r, 25) or r.get("cinder") in ("1", "True", "true")]
        ),
        "cinder_maw": room_subset([r for r in rs if has_kind(r, 14)]),
        "cinder_kite": room_subset([r for r in rs if has_kind(r, 25)]),
        "fold_star": room_subset([r for r in rs if has_kind(r, 11)]),
        "no_status_carriers": room_subset(
            [r for r in rs if not (has_kind(r, 11) or has_kind(r, 14) or has_kind(r, 25))]
        ),
        "by_skill": {},
        "by_hero": {},
        "by_fixture": {},
    }
    for skill in SKILLS:
        out["by_skill"][skill] = room_subset([r for r in rs if r.get("skill") == skill])
    for hero in HEROES:
        out["by_hero"][hero] = room_subset([r for r in rs if r.get("hero") == hero])
    fixtures = collections.defaultdict(list)
    for r in rs:
        fixtures[r.get("fixture") or "?"].append(r)
    for name, xs in sorted(fixtures.items()):
        kinds = sorted({k for r in xs for k in str(r.get("enemy_kinds") or "").replace(",", " ").split() if k})
        rec = room_subset(xs)
        rec["enemy_kinds"] = kinds
        rec["cinder"] = any(k in {"14", "25"} for k in kinds) or any(
            r.get("cinder") in ("1", "True", "true") for r in xs
        )
        rec["fold_star"] = "11" in kinds
        out["by_fixture"][name] = rec
    return out


DEFAULT_NOTES = {
    "684bac5c": [
        "Official balance_arena.py and balance_rooms.py on 684bac5c (after #217 Burn DoT floor / attack halving, #218, #219 Confusion). This is the Player baseline and the commit immediately before #221 (Neon perf pass).",
        "Arena: 5 heroes × 3 skills (bot, skilled, average) × 4 seeds × boss+entry, Easy and Normal.",
        "Rooms: 80 fixtures per difficulty (incl. Cinder Maw/Kite and Fold Star) × 3 skills × 2 seeds = 480 fights each.",
        "Cinder Rex is the stage 3 colossus (boss_hp_start 240). Burn carriers: Cinder Maw (14), Cinder Kite (25). Stop carrier: Fold Star (11).",
        "death_kind comes from the official room harness (status at death). Arena deaths used death_status_active / death_status_kind; those fields were empty in this sweep because Cinder Rex and foyer slices landed no harmful statuses.",
        "Contact-only means a death with empty/none death_kind and no death_chain. Burn-involved / Stop-involved are overlapping flags (death_kind or chain). Lethal Poison/Bleed is death_kind poison/bleed or a dot_kill chain (not present on this build; Poison/Bleed were not lethal).",
    ],
    "3a910dbe": [
        "Official balance_arena.py and balance_rooms.py on 3a910dbe (PR #221 Neon perf pass). Same Burn / Poison / Bleed / Stop rules as 684bac5c: Poison and Bleed are not lethal, Burn still floors at 1 HP. This midpoint isolates the perf pass from #227.",
        "Same method as the 684bac5c Player sweep: Arena 5 heroes × 3 skills × 4 seeds × boss+entry, Easy and Normal; rooms 80 fixtures × 3 skills × 2 seeds = 480 fights each.",
        "Cinder Rex is the stage 3 colossus (boss_hp_start 240). Burn carriers: Cinder Maw (14), Cinder Kite (25). Stop carrier: Fold Star (11).",
        "3a910dbe is 684bac5c plus #221 only. A 684→3a91 contact delta can be attributed to the perf pass. A 3a91→805 delta is #227 (Burn proc trim + lethal Poison/Bleed).",
    ],
    "805476ea": [
        "Official balance_arena.py and balance_rooms.py on 805476ea (PR #227, current main at the time of the sweep): Cinder Maw/Kite Burn proc trimmed 42/16 → 12/5 (Normal/Easy); Poison and Bleed can take the last half-heart; Burn still floors at 1 HP and still halves ATK. Stop, Rex, and generic hostile proc are unchanged by #227.",
        "Same method as the 684bac5c Player sweep: Arena 5 heroes × 3 skills × 4 seeds × boss+entry, Easy and Normal; rooms 80 fixtures × 3 skills × 2 seeds = 480 fights each.",
        "Cinder Rex is the stage 3 colossus (boss_hp_start 240). Burn carriers: Cinder Maw (14), Cinder Kite (25). Stop carrier: Fold Star (11).",
        "New official chain token on this build: dot_kill (a Poison or Bleed tick took the last HP). dot_pinned_then_hit is still the #217 Burn floor (DoT stops at 1 HP, then a hit finishes the run). stop_then_hit is a Stop proc followed by a hit while frozen.",
        "805476ea is #221 (Neon perf) plus #227 (Burn trim + lethal Poison/Bleed) on top of 684bac5c. A contact-death change versus 684bac5c cannot be attributed to #221 alone.",
    ],
}


def summarize_build(base: Path, build: str, rom_sha: str, notes=None):
    base = Path(base)
    return {
        "schema": SCHEMA_BUILD,
        "build": build,
        "rom_sha256": rom_sha,
        "title": "Stage 3 death breakdown and Cinder Rex matrix",
        "notes": list(notes if notes is not None else DEFAULT_NOTES.get(build, [])),
        "csv": {
            "arena_easy": str(base / "arena-s3-easy.csv"),
            "arena_normal": str(base / "arena-s3-normal.csv"),
            "rooms_easy": str(base / "rooms-s3-easy.csv"),
            "rooms_normal": str(base / "rooms-s3-normal.csv"),
        },
        "arena": {
            "easy": analyze_arena(base / "arena-s3-easy.csv", "easy"),
            "normal": analyze_arena(base / "arena-s3-normal.csv", "normal"),
        },
        "rooms": {
            "easy": analyze_rooms(base / "rooms-s3-easy.csv", "easy"),
            "normal": analyze_rooms(base / "rooms-s3-normal.csv", "normal"),
        },
    }


def _db(block):
    return (block or {}).get("death_break") or {}


def _oc(block, key):
    return int(((block or {}).get("outcomes") or {}).get(key, 0))


def compare_rooms(old, new):
    def pack(label, a, b):
        ad, bd = _db(a), _db(b)
        return {
            "subset": label,
            "old_n": a.get("n", 0),
            "new_n": b.get("n", 0),
            "old_died": a.get("died", a.get("deaths", 0)),
            "new_died": b.get("died", b.get("deaths", 0)),
            "old_contact_only": ad.get("contact_only", 0),
            "new_contact_only": bd.get("contact_only", 0),
            "d_contact_only": bd.get("contact_only", 0) - ad.get("contact_only", 0),
            "old_burn_involved": ad.get("burn_involved", 0),
            "new_burn_involved": bd.get("burn_involved", 0),
            "d_burn_involved": bd.get("burn_involved", 0) - ad.get("burn_involved", 0),
            "old_stop_involved": ad.get("stop_involved", 0),
            "new_stop_involved": bd.get("stop_involved", 0),
            "d_stop_involved": bd.get("stop_involved", 0) - ad.get("stop_involved", 0),
            "old_lethal_poison_bleed": ad.get("lethal_poison_bleed", 0),
            "new_lethal_poison_bleed": bd.get("lethal_poison_bleed", 0),
            "d_lethal_poison_bleed": bd.get("lethal_poison_bleed", 0) - ad.get("lethal_poison_bleed", 0),
            "old_outcomes": a.get("outcomes") or {},
            "new_outcomes": b.get("outcomes") or {},
            "old_death_kind": a.get("death_kind") or {},
            "new_death_kind": b.get("death_kind") or {},
            "old_death_chain": a.get("death_chain") or {},
            "new_death_chain": b.get("death_chain") or {},
        }

    rows_out = [
        pack("all", old, new),
        pack("cinder_maw_kite", old.get("cinder") or {}, new.get("cinder") or {}),
        pack("cinder_maw", old.get("cinder_maw") or {}, new.get("cinder_maw") or {}),
        pack("cinder_kite", old.get("cinder_kite") or {}, new.get("cinder_kite") or {}),
        pack("fold_star", old.get("fold_star") or {}, new.get("fold_star") or {}),
        pack("no_status_carriers", old.get("no_status_carriers") or {}, new.get("no_status_carriers") or {}),
    ]
    fixtures = []
    old_fx, new_fx = old.get("by_fixture") or {}, new.get("by_fixture") or {}
    names = sorted(set(old_fx) | set(new_fx))
    for name in names:
        rec = pack(name, old_fx.get(name) or {}, new_fx.get(name) or {})
        rec["enemy_kinds"] = (new_fx.get(name) or old_fx.get(name) or {}).get("enemy_kinds") or []
        rec["cinder"] = bool((new_fx.get(name) or old_fx.get(name) or {}).get("cinder"))
        rec["fold_star"] = bool((new_fx.get(name) or old_fx.get(name) or {}).get("fold_star"))
        fixtures.append(rec)
    changed = [f for f in fixtures if f["d_contact_only"] or f["old_died"] != f["new_died"]]
    return {"subsets": rows_out, "fixtures_changed": changed, "fixtures_all": fixtures}


def compare_arena(old, new):
    def pack(label, a, b):
        ad, bd = _db(a), _db(b)
        return {
            "kind": label,
            "old_n": a.get("n", 0),
            "new_n": b.get("n", 0),
            "old_cleared": _oc(a, "cleared"),
            "new_cleared": _oc(b, "cleared"),
            "old_died": a.get("deaths", _oc(a, "died")),
            "new_died": b.get("deaths", _oc(b, "died")),
            "old_timeout": _oc(a, "timeout"),
            "new_timeout": _oc(b, "timeout"),
            "old_contact_only": ad.get("contact_only", 0),
            "new_contact_only": bd.get("contact_only", 0),
            "d_contact_only": bd.get("contact_only", 0) - ad.get("contact_only", 0),
            "old_burn_involved": ad.get("burn_involved", 0),
            "new_burn_involved": bd.get("burn_involved", 0),
            "old_stop_involved": ad.get("stop_involved", 0),
            "new_stop_involved": bd.get("stop_involved", 0),
            "old_lethal_poison_bleed": ad.get("lethal_poison_bleed", 0),
            "new_lethal_poison_bleed": bd.get("lethal_poison_bleed", 0),
            "old_status_harmful": a.get("status_harmful", 0),
            "new_status_harmful": b.get("status_harmful", 0),
        }

    return {
        "boss": pack("boss", old.get("boss") or {}, new.get("boss") or {}),
        "entry": pack("entry", old.get("entry") or {}, new.get("entry") or {}),
    }


def compare_builds(baseline, current, issue_228_notes=None):
    out = {
        "schema": SCHEMA_COMPARE,
        "baseline_build": baseline.get("build"),
        "current_build": current.get("build"),
        "baseline_rom_sha256": baseline.get("rom_sha256"),
        "current_rom_sha256": current.get("rom_sha256"),
        "title": "Stage 3 balance comparison",
        "difficulties": {},
        "issue_228": {
            "title": "Perf pass #221 may have raised contact deaths",
            "notes": issue_228_notes or [],
        },
        "builds": {
            baseline["build"]: baseline,
            current["build"]: current,
        },
    }
    for diff in ("easy", "normal"):
        out["difficulties"][diff] = {
            "rooms": compare_rooms(
                (baseline.get("rooms") or {}).get(diff) or {},
                (current.get("rooms") or {}).get(diff) or {},
            ),
            "arena": compare_arena(
                (baseline.get("arena") or {}).get(diff) or {},
                (current.get("arena") or {}).get(diff) or {},
            ),
        }
    return out


def _died(block):
    return int(block.get("died", block.get("deaths", 0)) or 0)


def three_way_subset(label, a, b, c):
    ad, bd, cd = _db(a), _db(b), _db(c)
    def trip(key, src="db"):
        if src == "db":
            xs = (ad.get(key, 0), bd.get(key, 0), cd.get(key, 0))
        elif src == "died":
            xs = (_died(a), _died(b), _died(c))
        else:
            xs = (a.get(key, 0), b.get(key, 0), c.get(key, 0))
        return {"v684": xs[0], "v3a91": xs[1], "v805": xs[2], "d221": xs[1] - xs[0], "d227": xs[2] - xs[1]}

    return {
        "subset": label,
        "n": c.get("n") or b.get("n") or a.get("n") or 0,
        "died": trip("died", "died"),
        "contact_only": trip("contact_only"),
        "burn_involved": trip("burn_involved"),
        "stop_involved": trip("stop_involved"),
        "lethal_poison_bleed": trip("lethal_poison_bleed"),
        "cleared": trip("cleared") if "cleared" in ((a.get("outcomes") or {}) | (b.get("outcomes") or {}) | (c.get("outcomes") or {})) or True else None,
        "outcomes_684": a.get("outcomes") or {},
        "outcomes_3a91": b.get("outcomes") or {},
        "outcomes_805": c.get("outcomes") or {},
        "death_kind_684": a.get("death_kind") or {},
        "death_kind_3a91": b.get("death_kind") or {},
        "death_kind_805": c.get("death_kind") or {},
        "death_chain_684": a.get("death_chain") or {},
        "death_chain_3a91": b.get("death_chain") or {},
        "death_chain_805": c.get("death_chain") or {},
    }


def three_way_arena_kind(label, a, b, c):
    rec = three_way_subset(label, a, b, c)
    rec["cleared"] = {
        "v684": _oc(a, "cleared"),
        "v3a91": _oc(b, "cleared"),
        "v805": _oc(c, "cleared"),
        "d221": _oc(b, "cleared") - _oc(a, "cleared"),
        "d227": _oc(c, "cleared") - _oc(b, "cleared"),
    }
    rec["timeout"] = {
        "v684": _oc(a, "timeout"),
        "v3a91": _oc(b, "timeout"),
        "v805": _oc(c, "timeout"),
        "d221": _oc(b, "timeout") - _oc(a, "timeout"),
        "d227": _oc(c, "timeout") - _oc(b, "timeout"),
    }
    rec["status_harmful"] = {
        "v684": a.get("status_harmful", 0),
        "v3a91": b.get("status_harmful", 0),
        "v805": c.get("status_harmful", 0),
    }
    return rec


def three_way_compare(baseline, midpoint, current):
    out = {"rooms": {}, "arena": {}}
    for diff in ("easy", "normal"):
        ro = (baseline.get("rooms") or {}).get(diff) or {}
        rm = (midpoint.get("rooms") or {}).get(diff) or {}
        rc = (current.get("rooms") or {}).get(diff) or {}
        subsets = [
            three_way_subset("all", ro, rm, rc),
            three_way_subset("cinder_maw_kite", ro.get("cinder") or {}, rm.get("cinder") or {}, rc.get("cinder") or {}),
            three_way_subset("cinder_maw", ro.get("cinder_maw") or {}, rm.get("cinder_maw") or {}, rc.get("cinder_maw") or {}),
            three_way_subset("cinder_kite", ro.get("cinder_kite") or {}, rm.get("cinder_kite") or {}, rc.get("cinder_kite") or {}),
            three_way_subset("fold_star", ro.get("fold_star") or {}, rm.get("fold_star") or {}, rc.get("fold_star") or {}),
            three_way_subset("no_status_carriers", ro.get("no_status_carriers") or {}, rm.get("no_status_carriers") or {}, rc.get("no_status_carriers") or {}),
        ]
        ao = (baseline.get("arena") or {}).get(diff) or {}
        am = (midpoint.get("arena") or {}).get(diff) or {}
        ac = (current.get("arena") or {}).get(diff) or {}
        out["rooms"][diff] = {"subsets": subsets}
        out["arena"][diff] = {
            "boss": three_way_arena_kind("boss", ao.get("boss") or {}, am.get("boss") or {}, ac.get("boss") or {}),
            "entry": three_way_arena_kind("entry", ao.get("entry") or {}, am.get("entry") or {}, ac.get("entry") or {}),
        }
    return out



def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", type=Path, required=True, help="Directory of CSVs for the current (or only) build")
    ap.add_argument("--build", required=True)
    ap.add_argument("--rom-sha", required=True)
    ap.add_argument("--out", type=Path, help="Where to write this build's summary.json (default: BASE/summary.json)")
    ap.add_argument("--baseline-base", type=Path, help="Directory of CSVs for the kept baseline")
    ap.add_argument("--baseline-build", default="684bac5c")
    ap.add_argument("--baseline-rom-sha", default="519f58d9e31205a8911062b48c781a65df0c91d166b6b29813de03870387ac7f")
    ap.add_argument("--midpoint-base", type=Path, help="Directory of CSVs for the #221 midpoint (3a910dbe)")
    ap.add_argument("--midpoint-build", default="3a910dbe")
    ap.add_argument("--midpoint-rom-sha", default="")
    ap.add_argument("--compare-out", type=Path, help="Where to write the comparison document")
    args = ap.parse_args(argv)

    current = summarize_build(args.base, args.build, args.rom_sha)
    out = args.out or (args.base / "summary.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(current, indent=2) + "\n")
    print("wrote", out, "bytes", out.stat().st_size)

    if args.baseline_base:
        baseline = summarize_build(args.baseline_base, args.baseline_build, args.baseline_rom_sha)
        bout = args.baseline_base / "summary.json"
        bout.write_text(json.dumps(baseline, indent=2) + "\n")
        print("wrote", bout, "bytes", bout.stat().st_size)
        cmp_out = args.compare_out or (args.base.parent / "summary.json")
        cmp_out.parent.mkdir(parents=True, exist_ok=True)
        cmp = compare_builds(baseline, current)
        if args.midpoint_base:
            mid = summarize_build(args.midpoint_base, args.midpoint_build, args.midpoint_rom_sha)
            mout = args.midpoint_base / "summary.json"
            mout.write_text(json.dumps(mid, indent=2) + "\n")
            print("wrote", mout, "bytes", mout.stat().st_size)
            cmp["midpoint_build"] = mid["build"]
            cmp["midpoint_rom_sha256"] = mid.get("rom_sha256")
            cmp["builds"][mid["build"]] = mid
            cmp["three_way"] = three_way_compare(baseline, mid, current)
        cmp_out.write_text(json.dumps(cmp, indent=2) + "\n")
        print("wrote", cmp_out, "bytes", cmp_out.stat().st_size)
        for diff in ("easy", "normal"):
            all_row = cmp["difficulties"][diff]["rooms"]["subsets"][0]
            rex = cmp["difficulties"][diff]["arena"]["boss"]
            print(
                f"{diff}: rooms died {all_row['old_died']}->{all_row['new_died']} "
                f"contact {all_row['old_contact_only']}->{all_row['new_contact_only']} "
                f"(d{all_row['d_contact_only']:+d}) "
                f"burn {all_row['old_burn_involved']}->{all_row['new_burn_involved']} "
                f"stop {all_row['old_stop_involved']}->{all_row['new_stop_involved']} "
                f"pb {all_row['old_lethal_poison_bleed']}->{all_row['new_lethal_poison_bleed']}; "
                f"Rex died {rex['old_died']}->{rex['new_died']} "
                f"contact {rex['old_contact_only']}->{rex['new_contact_only']}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
