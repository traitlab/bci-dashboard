"""Read out a closed round: prioritised arm against the random control.

Every batch carries `CONTROL_FRACTION` of its rows drawn at random from the photos not
sent yet, marked `picked_by == control`. Once the botanists' labels are in the GT file,
those rows are a free randomised comparison, round by round. Per arm this prints n, the share of labels that differ from the
model's first guess (corrections), the rows whose species was new to the
project at that round, and the rows whose species was long-tail (fewer than
`WELL_SAMPLED_MIN_N` labelled crowns before the round), each with a Wilson 95%
interval. The interval is the point: a round holds a handful of control rows.

Inputs, all local, no network:
  --ledger-dir  the round ledgers `dispatch_round.py` wrote, input/rounds/round_<N>.csv
           (round, picked_by, predicted_species). They are the record of what each
           round sent; send_batches.csv is rewritten every refresh and is not.
           Rows with no `predicted_species` have no first guess and are left out of
           the correction rate only.
  --sent / --queue  explicit overrides: a send_batches.csv (its batch_id read as the
           round) and a send_first_queue.csv whose `predicted_species` wins.
  --gt     gt_dominant_taxon.csv, which `close_round.py` appends to.

A round is closed when at least one of its sent rows has a label in the GT file;
otherwise this prints "pending" and exits 0. "New" and "long-tail" are judged
against the GT rows that are not in this round or any later one. Long-tail
includes new species.

Writes build/tables/round_readout.csv (one row per scope and arm) for a page step,
from --all only: a single --round run prints and leaves the file alone.

Usage:
    python labelling/read_round.py --round 1
    python labelling/read_round.py --all
"""
from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "dashboard"))

import core
from score_confirmatory import wilson

ARMS = ("prioritised", "control")
COUNTS = ("n_sent", "n_labelled", "n_with_guess", "corrections", "new_rows", "long_tail_rows")
OUT_COLUMNS = ["scope", "status", "arm", "n_sent", "n_labelled", "n_with_guess",
               "corrections", "corrections_lo", "corrections_hi",
               "new_rows", "new_lo", "new_hi", "new_species",
               "long_tail_rows", "long_tail_lo", "long_tail_hi"]


def read_rows(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def arm_of(row: dict) -> str:
    return "control" if (row.get("picked_by") or "").strip() == "control" else "prioritised"


def _norm(name: str) -> str:
    return (name or "").strip().lower()


def read_round(sent: list[dict], gt: dict[str, str], guess: dict[str, str],
               round_no: int) -> dict:
    """One round's per-arm counts. `status` is pending when nothing is labelled."""
    mine = [r for r in sent if r["round"].strip() == str(round_no)]
    later = {r["global_key"] for r in sent
             if r["round"].strip().isdigit() and int(r["round"]) >= round_no}
    before = Counter(_norm(s) for k, s in gt.items() if k not in later)
    arms = {a: {**dict.fromkeys(COUNTS, 0), "new_species": set()} for a in ARMS}
    for r in mine:
        c = arms[arm_of(r)]
        c["n_sent"] += 1
        label = _norm(gt.get(r["global_key"], ""))
        if not label:
            continue
        c["n_labelled"] += 1
        first = _norm(guess.get(r["global_key"], ""))
        if first:
            c["n_with_guess"] += 1
            c["corrections"] += label != first
        if before[label] == 0:
            c["new_rows"] += 1
            c["new_species"].add(label)
        c["long_tail_rows"] += before[label] < core.WELL_SAMPLED_MIN_N
    closed = any(c["n_labelled"] for c in arms.values())
    return {"round": round_no, "status": "closed" if closed else "pending", "arms": arms}


def pool(results: list[dict]) -> dict:
    """Closed rounds summed per arm; new species counted once per (round, species)."""
    arms = {a: {**dict.fromkeys(COUNTS, 0), "new_species": 0} for a in ARMS}
    for res in results:
        for a, c in res["arms"].items():
            for k in COUNTS:
                arms[a][k] += c[k]
            arms[a]["new_species"] += len(c["new_species"])
    return arms


def out_row(scope: str, arm: str, c: dict) -> dict:
    ns = c["new_species"] if isinstance(c["new_species"], int) else len(c["new_species"])
    row = {"scope": scope, "status": "closed", "arm": arm, "new_species": ns,
           **{k: c[k] for k in COUNTS}}
    for key, hits, n in (("corrections", c["corrections"], c["n_with_guess"]),
                         ("new", c["new_rows"], c["n_labelled"]),
                         ("long_tail", c["long_tail_rows"], c["n_labelled"])):
        lo, hi = wilson(hits, n) if n else ("", "")
        row[f"{key}_lo"], row[f"{key}_hi"] = (round(lo, 4), round(hi, 4)) if n else ("", "")
    return row


def render(title: str, rows: list[dict]) -> str:
    def cell(r, hits, n, key):
        return f"{r[hits]}/{r[n]} [{r[key + '_lo']:.0%},{r[key + '_hi']:.0%}]" if r[n] else "-"

    out = [title,
           f"  {'arm':12} {'n':>4} {'corrections':>22} {'new to project':>22} {'long-tail':>22}"]
    for r in rows:
        out.append(f"  {r['arm']:12} {r['n_labelled']:>4} "
                   f"{cell(r, 'corrections', 'n_with_guess', 'corrections'):>22} "
                   f"{cell(r, 'new_rows', 'n_labelled', 'new'):>22} "
                   f"{cell(r, 'long_tail_rows', 'n_labelled', 'long_tail'):>22}"
                   f"  ({r['new_species']} new species)")
    out.append("  Wilson 95%. Small arms give wide intervals; read them, not the point share.")
    return "\n".join(out)


def parse_args():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    which = ap.add_mutually_exclusive_group(required=True)
    which.add_argument("--round", type=int, help="round to read (the ledger's round)")
    which.add_argument("--all", action="store_true", help="pool every closed round")
    ap.add_argument("--ledger-dir", type=Path, default=REPO / "input" / "rounds")
    ap.add_argument("--sent", type=Path, help="send_batches.csv instead of the ledgers")
    ap.add_argument("--queue", type=Path, help="send_first_queue.csv for the first guesses")
    ap.add_argument("--gt", type=Path, default=Path(core.GT_CSV))
    ap.add_argument("--out", type=Path, default=REPO / "build/tables/round_readout.csv")
    return ap.parse_args()


def main() -> None:
    args = parse_args()
    if args.sent:
        if not args.sent.exists():
            sys.exit(f"ERROR: {args.sent} not found.")
        sent = [{**r, "round": r["batch_id"]} for r in read_rows(args.sent)]
    else:
        sent = [r for p in sorted(args.ledger_dir.glob("round_*.csv")) for r in read_rows(p)]
        if not sent and args.all:
            # Nothing dispatched yet: the page already says pending without the file.
            print(f"no round ledger rows in {args.ledger_dir}; nothing to read")
            return
        if not sent:
            sys.exit(f"ERROR: no round ledger rows in {args.ledger_dir}.")
    # No GT file yet means no round has been closed: pending, not an error.
    gt = ({r["global_key"]: r["wcvp_canonical_name"] for r in read_rows(args.gt)}
          if args.gt.exists() else {})
    guess = {r["global_key"]: r.get("predicted_species") or "" for r in sent}
    if args.queue and args.queue.exists():
        guess.update({r["global_key"]: r["predicted_species"] for r in read_rows(args.queue)})
    if args.round is not None:
        wanted = [args.round]
    else:
        wanted = sorted({int(r["round"]) for r in sent if r["round"].strip().isdigit()})
    results = [read_round(sent, gt, guess, n) for n in wanted]
    closed = [r for r in results if r["status"] == "closed"]
    out = []
    for r in results:
        if r["status"] == "pending" and args.all:
            continue  # --all lists the closed rounds; the rest are rounds not yet read
        if r["status"] == "pending":
            print(f"round {r['round']}: pending (no labels for its sent rows in {args.gt.name})")
            out.append({"scope": str(r["round"]), "status": "pending"})
            continue
        rows = [out_row(str(r["round"]), a, r["arms"][a]) for a in ARMS]
        print(render(f"round {r['round']}", rows))
        out += rows
    if args.all:
        if closed:
            rows = [out_row("pooled", a, c) for a, c in pool(closed).items()]
            print(render(f"pooled over rounds {[r['round'] for r in closed]}", rows))
            out += rows
        else:
            print("pooled: pending (no round closed)")
            out.append({"scope": "pooled", "status": "pending"})
    if not args.all:
        return  # a lone round must not overwrite the page file's other rounds
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, OUT_COLUMNS, restval="")
        w.writeheader()
        w.writerows(out)


if __name__ == "__main__":
    main()
