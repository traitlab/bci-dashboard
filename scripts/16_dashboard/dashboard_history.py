"""The model-health snapshots on disk: verify the build against them, plot the trend.

Everything that reads 16_model_health.py's *output* lives here, so the renderer
only computes and renders. Two jobs, both about the snapshot folders:

``verify_snapshot`` aborts the build when the page disagrees with the current
snapshot's CSVs or run log, and ``load_trend``/``Trend`` turn the whole series of
snapshots into charts.

The page is meant to be re-run over months. Each run of 16_model_health.py
leaves a snapshot folder ``bci_workshop_labelbox_plantnet-docs/
model-health-<date>/``; this module folds every one of them into a single
append-only ``history.csv`` beside the newest snapshot's CSVs, so the page
reads one small file instead of re-parsing every snapshot.

The subtlety this module exists to protect: Pl@ntNet ships a new model every
few months, on its own schedule rather than the labelling programme's. A metric
that moves can therefore mean a new model OR more labels. Every snapshot
carries a ``model_tag``, the points where it changes are marked distinctly in
both the sparklines and the two-series chart, and the caption names which axis
moved. Stdlib only, no network.
"""

from __future__ import annotations

import csv
import glob
import os
import re

import health_core as hc
from dashboard_assets import esc, panel, pctf, svg_spark, svg_two_series

HISTORY_COLS = ["snapshot_date", "model_tag", "n_crowns", "metric", "value"]
SNAPSHOT_DIR = re.compile(r"model-health-(\d{4}-\d{2}-\d{2})$")


def verify_snapshot(directory, *, per_species, buckets, bins_all, trend, n_crowns, macro1,
                    micro1, never_all, unscoreable, strict_hits):
    """Abort the build if the page disagrees with 16_model_health.py's snapshot."""
    def fail(msg):
        raise SystemExit(f"VERIFY FAIL: {msg}")

    def close(a, b, tol=5e-5):
        return abs(float(a) - float(b)) <= tol

    checks = []
    path = os.path.join(directory, "per_species_health.csv")
    ref = {r["species"]: r for r in hc.read_csv_rows(path)}
    if len(ref) != len(per_species):
        fail(f"{len(per_species)} species here vs {len(ref)} in {path}")
    for row in per_species:
        r = ref.get(row["species"])
        if r is None:
            fail(f"species {row['species']!r} absent from {path}")
        if int(r["n_labelled_crowns"]) != row["n_labelled_crowns"]:
            fail(f"labelled crowns for {row['species']!r}")
        for col in ("top1_accuracy", "top5_accuracy"):
            if not close(r[col], row[col]):
                fail(f"{col} for {row['species']!r}")
    checks.append(f"per_species_health.csv: {len(ref)} species, crowns and both rates match")

    for r in hc.read_csv_rows(os.path.join(directory, "support_buckets.csv")):
        b = buckets.get(r["support_bucket"])
        if b is None:
            fail(f"labelled-crown group {r['support_bucket']!r} missing here")
        if int(r["n_crowns"]) != b["n_crowns"] or int(r["n_species"]) != b["n_species"]:
            fail(f"labelled-crown group {r['support_bucket']!r} counts")
        if not close(r["top1_accuracy"], b["c1"] / b["n_crowns"]):
            fail(f"labelled-crown group {r['support_bucket']!r} first-guess rate")
    checks.append(f"support_buckets.csv: {len(buckets)} labelled-crown groups match")

    path = os.path.join(directory, "confidence_calibration.csv")
    ref_bins = {r["band"]: r for r in hc.read_csv_rows(path)
                if r["row_type"] == "bin" and r["scope"] == "all_species_level_gt"}
    for band, n, k in bins_all:
        r = ref_bins.get(band)
        if r is None:
            fail(f"confidence band {band!r} absent from {path}")
        if int(r["n_crowns"]) != n or int(r["n_correct"]) != k:
            fail(f"confidence band {band!r} counts")
    checks.append(f"confidence_calibration.csv: {len(bins_all)} confidence bands match")

    # These three live in the run log's prose, not in any CSV, and they are the numbers the
    # page states on denominators the CSVs never use. Checking them here is what once caught
    # the report and the CSVs disagreeing by two crowns.
    path = os.path.join(directory, "run_log.txt")
    with open(path, encoding="utf-8") as f:
        log = f.read()
    for pat, here, what in (
            (r"^\s*(\d+) GT crowns across \d+ species can NEVER", never_all,
             "crowns the model can never name, over every label"),
            (r"excludes the (\d+) crowns that are unscoreable", unscoreable,
             "unscoreable crowns inside the evaluated set"),
            (r"strict top-1\s*:\s*[\d.]+%\s*\((\d+)/", strict_hits,
             "first guesses right without name reconciliation")):
        m = re.search(pat, log, re.M)
        if m is None:
            fail(f"no line for {what} in {path}")
        if int(m.group(1)) != here:
            fail(f"{what}: {here} here vs {m.group(1)} in {path}")
    checks.append(f"run_log.txt: the {never_all}-crown ceiling, the {unscoreable} unscoreable "
                  f"evaluated crowns and the {strict_hits}-hit unreconciled baseline match")

    checks.append(trend.check(n_crowns=n_crowns, macro1=macro1, micro1=micro1))
    return checks


def model_tag_of(snap_dir: str, fallback: str) -> str:
    """Which Pl@ntNet model iteration produced a snapshot.

    Read from that snapshot's own run_log.txt, which records the endpoint and
    config.yaml's ``single_model_run_name`` (currently ``v7.4-2026-03-27``).
    Those two strings are the only thing on disk that tells one Pl@ntNet
    iteration from the next, so the tag is ``<endpoint-slug>@<run-name>``. A
    log naming neither falls back to ``--model-tag``, never to an invented tag.
    """
    try:
        with open(os.path.join(snap_dir, "run_log.txt"), encoding="utf-8") as f:
            text = f.read()
    except OSError:
        return fallback
    run = re.search(r"single_model_run_name '([^']+)'", text)
    if not run:
        return fallback
    region = re.search(r"identify/([A-Za-z0-9-]+)", text)
    return f"{region.group(1)}@{run.group(1)}" if region else run.group(1)


def snapshot_rows(snap_dir: str) -> list[tuple[str, int, float]]:
    """(metric, n_crowns, value) for one snapshot, from its per-species CSV."""
    rows = hc.read_csv_rows(os.path.join(snap_dir, "per_species_health.csv"))
    n = sum(int(r["n_labelled_crowns"]) for r in rows)
    out = [("macro_top1", n, sum(float(r["top1_accuracy"]) for r in rows) / len(rows)),
           ("macro_top5", n, sum(float(r["top5_accuracy"]) for r in rows) / len(rows)),
           ("micro_top1", n, sum(int(r["n_correct_top1"]) for r in rows) / n),
           ("micro_top5", n, sum(int(r["n_correct_top5"]) for r in rows) / n)]
    return out + [(f"species:{r['species']}:top1", int(r["n_labelled_crowns"]),
                   float(r["top1_accuracy"])) for r in rows]


class Trend:
    """Every snapshot's headline and per-species rates, oldest first."""

    def __init__(self, path, rows):
        self.path = path
        tags, crowns, self.series = {}, {}, {}
        for r in rows:
            date = r["snapshot_date"]
            tags[date] = r["model_tag"]
            if r["metric"] == "micro_top1":
                crowns[date] = int(r["n_crowns"])
            self.series.setdefault(r["metric"], {})[date] = float(r["value"])
        self.dates = sorted(tags)
        self.snaps = [(d, tags[d], crowns.get(d, 0)) for d in self.dates]
        # Indices where the model iteration differs from the previous snapshot.
        self.marks = [i for i in range(1, len(self.snaps))
                      if self.snaps[i][1] != self.snaps[i - 1][1]]

    @property
    def tag(self) -> str:
        return self.snaps[-1][1] if self.snaps else "unknown"

    @property
    def latest(self) -> str:
        return self.snaps[-1][0] if self.snaps else "n/a"

    def spark(self, metric: str, empty: str = "no trend yet") -> str:
        got = self.series.get(metric, {})
        return svg_spark([got[d] for d in self.dates if d in got], self.marks, empty=empty)

    def check(self, *, n_crowns, macro1, micro1) -> str:
        """history.csv is append-only, so a re-measured snapshot would leave its
        stored trend point behind. Hold the newest point to the live numbers.
        Per-species rates are stored to 4 dp, so their mean carries that much
        rounding error."""
        if self.snaps:
            date = self.latest
            if self.snaps[-1][2] != n_crowns:
                stale(f"{self.snaps[-1][2]} crowns for {date}", n_crowns, self.path)
            for metric, got in (("macro_top1", macro1), ("micro_top1", micro1)):
                if abs(self.series[metric][date] - got) > 1e-4:
                    stale(f"{metric} for {date} is {self.series[metric][date]}",
                          got, self.path)
        return (f"history.csv: {len(self.snaps)} snapshot(s); the newest one's crown count "
                f"and both headline rates match")

    def render(self) -> str:
        """The trend panel. Degrades to a plain sentence on a single snapshot."""
        ask = ("<b>Check whether a number moved because the model changed or because more "
               "crowns were labelled.</b> The two look identical in a single number.")
        if len(self.snaps) < 2:
            return panel(
                "Trend over time: first snapshot, no trend yet", ask,
                f'<p class="note">Only one snapshot is on disk ({esc(self.latest)}), so '
                f'there is nothing to compare against. Re-run '
                f'<code>16_model_health.py</code> into a new '
                f'<code>model-health-&lt;date&gt;/</code> folder in a few months and the '
                f'charts and the small lines beside each headline number fill in.</p>',
                open_=True)
        acc = [self.series["macro_top1"][d] for d in self.dates]
        body = [svg_two_series(self.dates, acc, [c for _, _, c in self.snaps], self.marks,
                               a_name="accuracy per species", b_name="labelled crowns",
                               a_fmt=pctf, b_fmt=lambda v: f"{int(v):,}")]
        for i in self.marks:
            body.append(
                f'<p class="note"><strong>{esc(self.dates[i])}: new Pl@ntNet model '
                f'({esc(self.snaps[i - 1][1])} to {esc(self.snaps[i][1])}).</strong> Across '
                f'that step accuracy per species moved {100 * (acc[i] - acc[i - 1]):+.1f} '
                f'points and the labelled-crown count moved '
                f'{self.snaps[i][2] - self.snaps[i - 1][2]:+,}. Both axes moved, so this '
                f'step cannot tell you which one caused the other. Compare it only against '
                f'steps under one constant model.</p>')
        if not self.marks:
            body.append(f'<p class="note">The model tag is <code>{esc(self.tag)}</code> for '
                        f'all {len(self.snaps)} snapshots, so every movement here is more '
                        f'labels arriving under one constant model.</p>')
        body.append('<p class="note">A red ring marks a snapshot where the Pl@ntNet model '
                    'changed, on the small trend lines too. Never read a step across a red '
                    'ring as progress from labelling.</p>')
        return panel(f"Trend over {len(self.snaps)} snapshots, {len(self.marks)} Pl@ntNet "
                     f"model change(s) marked", ask, "\n".join(body), open_=True)


def stale(found, here, path):
    raise SystemExit(f"VERIFY FAIL: {found} in {path} vs {here} here. Delete that "
                     f"snapshot's rows and re-run.")


def load_trend(snap_dir: str, fallback_tag: str) -> Trend:
    """Append any snapshot missing from history.csv, then return the whole thing.

    Existing rows are never rewritten, so a snapshot's trend point is fixed the
    first time it is seen and ``Trend.check`` catches any later drift.
    """
    path = os.path.join(snap_dir, "history.csv")
    have = hc.read_csv_rows(path) if os.path.exists(path) else []
    seen = {(r["snapshot_date"], r["metric"]) for r in have}
    fresh = []
    for d in sorted(glob.glob(os.path.join(os.path.dirname(snap_dir), "model-health-*"))):
        m = SNAPSHOT_DIR.search(d)
        if not m or not os.path.exists(os.path.join(d, "per_species_health.csv")):
            continue
        tag = model_tag_of(d, fallback_tag)
        fresh += [dict(snapshot_date=m.group(1), model_tag=tag, n_crowns=k, metric=metric,
                       value=f"{v:.6f}")
                  for metric, k, v in snapshot_rows(d) if (m.group(1), metric) not in seen]
    if fresh:
        with open(path, "a", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=HISTORY_COLS)
            if not have:
                w.writeheader()
            w.writerows(fresh)
    return Trend(path, have + fresh)
