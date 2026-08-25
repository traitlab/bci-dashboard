"""The model-health snapshots on disk: verify the build against them, plot the trend.

Everything that reads measure.py's *output* lives here, so the renderer
only computes and renders. Two jobs, both about the snapshot folders:

``verify_snapshot`` aborts the build when the page disagrees with the current
snapshot's CSVs or run log, and ``load_trend``/``Trend`` turn the whole series of
snapshots into charts.

The page is meant to be re-run over months. Each run of measure.py
leaves a snapshot folder ``snapshots/model-health-<date>/``; this module folds
every one of them into a single
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
import datetime
import glob
import os
import re
from collections import Counter

import core as hc
from assets import (
    esc, orientation_ok, panel, pctf, svg_spark, svg_two_series, weight_pair_ok)

HISTORY_COLS = ["snapshot_date", "model_tag", "n_crowns", "metric", "value", "source"]
# Narrowest accuracy axis any chart may draw, so a one-point wobble looks like a
# wobble instead of filling the plot.
RATE_SPAN = 0.10
SNAPSHOT_DIR = re.compile(r"model-health-(\d{4}-\d{2}-\d{2})$")
SNAPSHOT_GLOB = "model-health-*"


def latest_snapshot_dir() -> str:
    """Newest model-health-<date>/ folder in the snapshot store.

    Both pages gate on a snapshot folder, and a gate aimed at a fixed date
    silently checks today's numbers against an old measurement and appends
    today's trend points to that old folder's history. The date is in the
    folder name, so sorting is unambiguous.
    """
    found = sorted(d for d in glob.glob(os.path.join(hc.SNAPSHOT_DIR, SNAPSHOT_GLOB))
                   if SNAPSHOT_DIR.search(d))
    if not found:
        raise SystemExit(
            f"VERIFY FAIL: no {SNAPSHOT_GLOB} folder under {hc.SNAPSHOT_DIR}")
    return found[-1]


def verify_snapshot(directory, *, per_species, buckets, bins_all, trend, n_crowns, macro1,
                    micro1, never_all, unscoreable, strict_hits,
                    queue_counts=None, n_no_answer=None, review_counts=None):
    """Abort the build if the page disagrees with measure.py's snapshot.

    ``queue_counts`` maps queue name to crown count over the unlabelled pool,
    ``n_no_answer`` counts unlabelled crowns whose candidate list came back
    empty, and ``review_counts`` is (crowns, distinct confusion pairs) for the
    high-confidence label disagreements. All three are checked against the two
    queue CSVs when given.
    """
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

    if n_no_answer is not None:
        m = re.search(r"unlabelled crowns with NO answer\s*:\s*(\d+)", log)
        if m is None:
            fail(f"no no-answer line in {path}")
        if int(m.group(1)) != n_no_answer:
            fail(f"no-answer unlabelled crowns: {n_no_answer} here vs {m.group(1)} in {path}")

    checks.append(trend.check(n_crowns=n_crowns, macro1=macro1, micro1=micro1))

    if queue_counts is not None:
        path = os.path.join(directory, "send_first_queue.csv")
        ref = Counter(r["queue"] for r in hc.read_csv_rows(path))
        for q, k in queue_counts.items():
            if ref.get(q, 0) != k:
                fail(f"send-first queue {q!r}: {k} here vs {ref.get(q, 0)} in {path}")
        if set(ref) - set(queue_counts):
            fail(f"send-first queues {sorted(set(ref) - set(queue_counts))} only in {path}")
        n_unlab = sum(ref.values())
        checks.append(f"send_first_queue.csv: {n_unlab:,} unlabelled crowns across "
                      f"{len(ref)} queues match")

        # send_batches.csv must be a species-homogeneous, capped-size repartition
        # of the exact same rows: same total, every batch one species and no
        # more than BATCH_SIZE of them, no global_key skipped or duplicated.
        bpath = os.path.join(directory, "send_batches.csv")
        brows = hc.read_csv_rows(bpath)
        by_batch: dict = {}
        for r in brows:
            by_batch.setdefault(r["batch_id"], []).append(r)
        for bid, rows in by_batch.items():
            if len(rows) > hc.BATCH_SIZE:
                fail(f"send_batches.csv batch {bid}: {len(rows)} rows exceeds "
                     f"BATCH_SIZE={hc.BATCH_SIZE}")
            species = {r["species_group"] for r in rows}
            if len(species) != 1:
                fail(f"send_batches.csv batch {bid}: mixes species {sorted(species)}")
        if len(brows) != n_unlab:
            fail(f"send_batches.csv: {len(brows)} rows vs {n_unlab} in {path}")
        if {r["global_key"] for r in brows} != {r["global_key"]
                                                 for r in hc.read_csv_rows(path)}:
            fail(f"send_batches.csv: global_key set does not match {path}")
        checks.append(f"send_batches.csv: {len(brows):,} rows in {len(by_batch)} batches, "
                      f"one species and at most {hc.BATCH_SIZE} rows each")

    if review_counts is not None:
        path = os.path.join(directory, "label_review_queue.csv")
        ref = hc.read_csv_rows(path)
        pairs = {(r["gt_species"], r["predicted_species"]) for r in ref}
        if len(ref) != review_counts[0]:
            fail(f"label review queue: {review_counts[0]} here vs {len(ref)} in {path}")
        if len(pairs) != review_counts[1]:
            fail(f"label review pairs: {review_counts[1]} here vs {len(pairs)} in {path}")
        checks.append(f"label_review_queue.csv: {len(ref)} crowns, {len(pairs)} confusion "
                      f"pairs match")

    if not orientation_ok():
        fail("charts are drawn upside down: a rising series must have falling y")
    if not weight_pair_ok():
        fail("the weighting bars are drawn wrong: a bigger share must be a wider band")
    checks.append("charts: a rising series is drawn rising and a bigger share is drawn wider")
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


def cache_dates(cache_dir: str) -> dict[str, str]:
    """Cache file stem -> the day its Pl@ntNet response landed on disk.

    The cached responses carry no timestamp of their own and neither ground
    truth CSV has a date column, so the file's own mtime is the only record of
    when each prediction arrived. It is a proxy: copying the cache with a tool
    that does not preserve mtimes would reset every date to the copy day. The
    reconstruction below refuses to invent a trend from a single date, and its
    newest point is checked against the live measurement, so a flattened cache
    shows as no history rather than as a false one.
    """
    out = {}
    for f in glob.glob(os.path.join(cache_dir, "*.json")):
        out[os.path.basename(f)[: -len(".json")]] = (
            datetime.date.fromtimestamp(os.path.getmtime(f)).isoformat())
    return out


def reconstructed_rows(sp_recs, cache_dir: str) -> list[tuple[str, str, int, float]]:
    """(date, metric, n_crowns, value) for each ingest day, cumulative.

    Model health was first measured on one day, so history.csv would hold one
    point and no trend. But the predictions arrived in batches, and every
    evaluated crown can be attributed to the batch that fetched it. Scoring the
    crowns fetched up to each batch date gives the numbers this page would have
    printed on that date, under the same frozen model. Returns nothing if any
    crown cannot be dated or if every crown shares one date.
    """
    when = cache_dates(cache_dir)
    dated = []
    for r in sp_recs:
        gk = r["global_key"]
        stem = gk[len(hc.GT_KEY_PREFIX):] if gk.startswith(hc.GT_KEY_PREFIX) else gk
        if stem not in when:
            return []
        dated.append((when[stem], r))
    cuts = sorted({d for d, _ in dated})
    if len(cuts) < 2:
        return []
    rows = []
    for cut in cuts:
        by: dict[str, list] = {}
        for d, r in dated:
            if d <= cut:
                by.setdefault(r["gt"], []).append(r)
        per = [(sp, len(rs),
                sum(1 for r in rs if r["ranked"][0][0] == sp),
                sum(1 for r in rs if sp in [b for b, _ in r["ranked"][:5]]))
               for sp, rs in by.items()]
        n = sum(m for _, m, _, _ in per)
        rows += [(cut, "macro_top1", n, sum(k1 / m for _, m, k1, _ in per) / len(per)),
                 (cut, "macro_top5", n, sum(k5 / m for _, m, _, k5 in per) / len(per)),
                 (cut, "micro_top1", n, sum(k1 for _, _, k1, _ in per) / n),
                 (cut, "micro_top5", n, sum(k5 for _, _, _, k5 in per) / n)]
        rows += [(cut, f"species:{sp}:top1", m, k1 / m) for sp, m, k1, _ in per]
    return rows


class Trend:
    """Every snapshot's headline and per-species rates, oldest first."""

    def __init__(self, path, rows):
        self.path = path
        tags, crowns, self.series, self.source = {}, {}, {}, {}
        for r in rows:
            date = r["snapshot_date"]
            tags[date] = r["model_tag"]
            self.source[date] = r.get("source") or "measured"
            if r["metric"] == "micro_top1":
                crowns[date] = int(r["n_crowns"])
            self.series.setdefault(r["metric"], {})[date] = float(r["value"])
        self.dates = sorted(tags)
        self.snaps = [(d, tags[d], crowns.get(d, 0)) for d in self.dates]
        self.rebuilt = [d for d in self.dates if self.source[d] == "reconstructed"]
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
        return svg_spark([got[d] for d in self.dates if d in got], self.marks, empty=empty,
                         span=RATE_SPAN)

    def check(self, *, n_crowns, macro1, micro1) -> str:
        """history.csv is append-only, so a re-measured snapshot would leave its
        stored trend point behind. Hold the newest point to the live numbers.
        Per-species rates are stored to 4 dp, so their mean carries that much
        rounding error."""
        # The newest measured point and the newest reconstructed point both cover
        # every evaluated crown, so both must equal the live numbers.
        for date in [d for d in (self.latest,) if self.snaps] + self.rebuilt[-1:]:
            if self.snaps[self.dates.index(date)][2] != n_crowns:
                stale(f"{self.snaps[self.dates.index(date)][2]} crowns for {date}",
                      n_crowns, self.path)
            for metric, got in (("macro_top1", macro1), ("micro_top1", micro1)):
                if abs(self.series[metric][date] - got) > 1e-4:
                    stale(f"{metric} for {date} is {self.series[metric][date]}",
                          got, self.path)
        return (f"history.csv: {len(self.snaps)} point(s), {len(self.rebuilt)} reconstructed "
                f"from ingest dates; the newest measured and newest reconstructed point both "
                f"match the live crown count and both headline rates")

    def _composition(self) -> str:
        """Both headline rates over the same window, and what a gap between them
        means. Reports what the numbers did rather than asserting a direction."""
        mac, mic = self.series.get("macro_top1", {}), self.series.get("micro_top1", {})
        d0, d1 = self.dates[0], self.dates[-1]
        if not all(d in s for s in (mac, mic) for d in (d0, d1)):
            return ""
        dm, di = 100 * (mac[d1] - mac[d0]), 100 * (mic[d1] - mic[d0])
        held = ("under one constant model" if not self.marks
                else "across a Pl@ntNet model change, so read it with that in mind")
        head = (f'<p class="note"><strong>Between {esc(d0)} and {esc(d1)} crown-weighted '
                f'top-1 moved {di:+.1f} points and per-species top-1 moved {dm:+.1f} '
                f'points</strong>, {held}. ')
        if dm * di < 0:
            tail = ('They moved in opposite directions, which is only possible because the '
                    'crown mix changed. The later batches added crowns of species that were '
                    'already covered, which lifts the crown-weighted number, plus a handful '
                    'of newly photographed rare species, which drags the per-species one '
                    'down. Neither move is the model learning: Pl@ntNet never sees these '
                    'labels.')
        else:
            tail = ('Watch the gap between the two rather than either one alone. The '
                    'crown-weighted number rises whenever more crowns of already well-covered '
                    'species arrive. Only the per-species number rises when coverage widens '
                    'to species the model handles badly.')
        return head + tail + "</p>"

    def _spark_key(self) -> str:
        """The one place on the page that explains the small trend lines.

        They are drawn beside each headline number and in every species row by
        other modules, so without a single key a reader meets an unlabelled
        squiggle four times before reaching this panel.

        The ring clause is conditional because the ring is. Describing a marker
        that no chart on the page draws sends the reader hunting for it, and it
        contradicts the sentence below that says the model tag never changed.
        """
        ring = (" A hollow red ring is a snapshot where the Pl@ntNet model changed."
                if self.marks else "")
        return (
            '<details><summary>How to read these trend lines</summary>'
            f'<p class="note">Left to right is snapshots, oldest to newest, one point per '
            f'snapshot ({len(self.snaps)} so far). Every line is scaled to its own range, '
            f'so a steep line beside one number is not a bigger move than a flat line '
            f'beside another, and an accuracy line never shows a range narrower than '
            f'{pctf(RATE_SPAN)}, so a small wobble is drawn as a wobble rather than '
            f'collapsing to nothing. The filled dot at the right end is the current '
            f'value.{ring} The lines in the species table read the same way, on that one '
            f'species, and only where the species has enough crowns for the rate to '
            f'mean anything.</p>'
            '</details>')

    def render(self, *, open_: bool = True) -> str:
        """The trend panel. Degrades to a plain sentence on a single snapshot.

        ``open_`` because only the first panel of a section is open on the full
        page, and which section this one lands in is the caller's decision.
        """
        ask = ("<b>Check whether a number moved because the model changed or because more "
               "crowns were labelled.</b> The two look identical in a single number.")
        if len(self.snaps) < 2:
            return panel(
                "Trend over time: first snapshot, no trend yet", ask,
                f'<p class="note">Only one snapshot is on disk ({esc(self.latest)}), so '
                f'there is nothing to compare against. Re-run '
                f'<code>measure.py</code> into a new '
                f'<code>model-health-&lt;date&gt;/</code> folder in a few months and the '
                f'charts and the small lines beside each headline number fill in, one '
                f'point per snapshot, showing accuracy per species against the '
                f'labelled-crown count with any Pl@ntNet model change marked in red.</p>',
                open_=open_, anchor="trend-over-time")
        acc = [self.series["macro_top1"][d] for d in self.dates]
        body = [svg_two_series(self.dates, acc, [c for _, _, c in self.snaps], self.marks,
                               a_name="accuracy per species", b_name="labelled crowns",
                               a_fmt=pctf, b_fmt=lambda v: f"{int(v):,}", a_span=RATE_SPAN)]
        body.append(
            '<p class="note"><strong>Reading the chart.</strong> The two lines sit on '
            'separate scales, so the vertical gap between them means nothing and only the '
            'shape of each line carries information. The number printed at each end of a '
            "line is that line's value on the oldest and the newest snapshot."
            + (' A dashed red rule and hollow rings mark a snapshot where the Pl@ntNet '
               'model changed.' if self.marks else '')
            + '</p>')
        body.append(self._spark_key())
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
                        f'all {len(self.snaps)} points, so every movement here is more '
                        f'crowns arriving under one constant model.</p>')
        body.append(self._composition())
        if self.rebuilt:
            body.append(
                f'<p class="note"><strong>Where these points come from.</strong> '
                f'{len(self.rebuilt)} of them ({esc(", ".join(self.rebuilt))}) were '
                f'reconstructed, not measured on the day. Every prediction file on disk '
                f'carries the day it was fetched, so each crown can be scored against the '
                f'batch it arrived in, giving the numbers this page would have printed on '
                f'those dates. The reconstruction re-uses today\'s predictions, so '
                f'it is honest about the data mix and silent about the model: if Pl@ntNet had '
                f'already changed, an older point would still be scored with the current '
                f'model.</p>')
        if self.marks:
            body.append('<p class="note"><strong>Never read a step across a red ring as '
                        'progress from labelling.</strong> A red ring marks a point where '
                        'the Pl@ntNet model changed, here and on the small trend lines '
                        'beside each headline number.</p>')
        title = f"Trend over {len(self.snaps)} points"
        if self.rebuilt:
            title += f", {len(self.rebuilt)} reconstructed from ingest dates"
        if self.marks:
            title += f", {len(self.marks)} Pl@ntNet model change(s) marked"
        # The title counts snapshots, which is exactly what grows over time.
        return panel(title, ask, "\n".join(body), open_=open_,
                     anchor="trend-over-time")


def stale(found, here, path):
    raise SystemExit(f"VERIFY FAIL: {found} in {path} vs {here} here. Delete that "
                     f"snapshot's rows and re-run.")


def load_trend(snap_dir: str, fallback_tag: str, *, sp_recs=None, cache_dir=None) -> Trend:
    """Append anything missing from history.csv, then return the whole thing.

    Two kinds of point go in: one per dated ``model-health-<date>/`` folder,
    measured when that folder was written, and one per prediction-ingest day,
    reconstructed from the cache. Existing rows are never rewritten, so a point
    is fixed the first time it is seen; a stored reconstructed point that no
    longer recomputes to its stored value is a hard failure, because that means
    the cache dates moved under it.
    """
    path = os.path.join(snap_dir, "history.csv")
    have = hc.read_csv_rows(path) if os.path.exists(path) else []
    seen = {(r["snapshot_date"], r["metric"]): r for r in have}
    fresh = []
    for d in sorted(glob.glob(os.path.join(os.path.dirname(snap_dir), "model-health-*"))):
        m = SNAPSHOT_DIR.search(d)
        if not m or not os.path.exists(os.path.join(d, "per_species_health.csv")):
            continue
        tag = model_tag_of(d, fallback_tag)
        fresh += [dict(snapshot_date=m.group(1), model_tag=tag, n_crowns=k, metric=metric,
                       value=f"{v:.6f}", source="measured")
                  for metric, k, v in snapshot_rows(d) if (m.group(1), metric) not in seen]
    if sp_recs and cache_dir:
        tag = model_tag_of(snap_dir, fallback_tag)
        for date, metric, k, v in reconstructed_rows(sp_recs, cache_dir):
            was = seen.get((date, metric))
            if was is None:
                fresh.append(dict(snapshot_date=date, model_tag=tag, n_crowns=k,
                                  metric=metric, value=f"{v:.6f}", source="reconstructed"))
            elif was.get("source") == "reconstructed" and abs(float(was["value"]) - v) > 1e-6:
                stale(f"reconstructed {metric} for {date} is {was['value']}", f"{v:.6f}", path)
    if fresh:
        with open(path, "a", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=HISTORY_COLS)
            if not have:
                w.writeheader()
            w.writerows(fresh)
    return Trend(path, have + fresh)
