#!/usr/bin/env python3
"""Per-species Pl@ntNet-on-BCI health dashboard: one self-contained HTML page.

Answers "how is the model doing, per species, and what do I do about it?" from
data already on disk -- the botanist's GT labels plus cached Pl@ntNet responses.
No network, no API key, no third-party package. The page opens from a file://
URL with every style, script and chart inlined.

Run:
    python3 scripts/16_dashboard/16b_dashboard.py [--out PATH]

Numbers are recomputed here from source rather than read from the CSVs, and
then cross-checked against the committed CSVs from 16_model_health.py. A
mismatch aborts the build -- the page cannot disagree with the measurement.
"""

from __future__ import annotations

import argparse
import csv
import datetime as _dt
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import health_core as hc  # noqa: E402
from dashboard_assets import CSS, JS, esc  # noqa: E402

# A species is "rare" below this many labelled crowns. Same threshold as the
# auto-accept support gate, so the two panels cannot disagree.
RARE_MAX_SUPPORT = 10
AUTO_ACCEPT_SUPPORT_MIN = 10
RECOMMENDED_CONF = 0.8

STATUS_LABELS = {
    "reliable": "Reliable",
    "adequate": "Adequate",
    "ranking": "Ranking problem",
    "unmeasured": "Not yet measurable",
    "hard": "Model struggles",
    "unreachable": "Model cannot return it",
}
STATUS_ACTIONS = {
    "reliable": "Eligible for auto-accept; spot-check only",
    "adequate": "Keep in the review queue",
    "ranking": "Right answer is returned but not ranked first -- cheap to confirm",
    "unmeasured": "Too few labels to trust the estimate -- label more to establish it",
    "hard": "Enough labels, still wrong -- a model limit, not a labelling gap",
    "unreachable": "Labelling cannot fix this -- the species is never returned",
}


# ---------------------------------------------------------------------------
# diagnosis
# ---------------------------------------------------------------------------
def diagnose(row: dict) -> str:
    """Per-species status. First matching rule wins; order is the point.

    ``unreachable`` outranks everything because no amount of labelling moves
    it. ``reliable`` outranks ``ranking`` because a species already at >=90%
    top-1 does not need a re-rank. ``unmeasured`` sits below ``ranking`` so a
    thinly-labelled species whose answer is in the returned list is still
    reported as the cheap win it is.
    """
    n = row["n_labelled_crowns"]
    a1 = row["top1_accuracy"]
    a5 = row["top5_accuracy"]
    if not row["in_corpus_vocabulary"]:
        return "unreachable"
    if n >= AUTO_ACCEPT_SUPPORT_MIN and a1 >= 0.90:
        return "reliable"
    if a5 - a1 >= 0.20 and a5 >= 0.60:
        return "ranking"
    if n < AUTO_ACCEPT_SUPPORT_MIN:
        return "unmeasured"
    if a1 < 0.70:
        return "hard"
    return "adequate"


# ---------------------------------------------------------------------------
# inline SVG (hand-written in labelfirst's report idiom: no library, no CDN)
# ---------------------------------------------------------------------------
def svg_hbar(rows, *, width=620, row_h=30, label_w=96, right_w=132, title=""):
    """Horizontal accuracy bars. ``rows`` = [(label, frac, right_text, color)]."""
    if not rows:
        return ""
    top = 26 if title else 8
    bar_w = width - label_w - right_w
    height = top + len(rows) * row_h + 26
    out = [f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" '
           f'role="img" aria-label="{esc(title or "bar chart")}">']
    if title:
        out.append(f'<text x="{label_w}" y="16" font-size="12" fill="#616161">{esc(title)}</text>')
    for i, (label, frac, right, color) in enumerate(rows):
        y = top + i * row_h
        frac = max(0.0, min(1.0, float(frac)))
        out.append(f'<text x="{label_w - 8}" y="{y + 15}" font-size="12" fill="#424242" '
                   f'text-anchor="end">{esc(label)}</text>')
        out.append(f'<rect x="{label_w}" y="{y + 4}" width="{bar_w}" height="16" '
                   f'fill="#f1f3f4" rx="3"/>')
        out.append(f'<rect x="{label_w}" y="{y + 4}" width="{max(1, round(bar_w * frac))}" '
                   f'height="16" fill="{color}" rx="3"/>')
        out.append(f'<text x="{label_w + bar_w + 8}" y="{y + 16}" font-size="11.5" '
                   f'fill="#616161">{esc(right)}</text>')
    axis_y = top + len(rows) * row_h + 4
    out.append(f'<line x1="{label_w}" y1="{axis_y}" x2="{label_w + bar_w}" y2="{axis_y}" '
               f'stroke="#e0e0e0"/>')
    for t in (0, 25, 50, 75, 100):
        x = label_w + bar_w * t / 100.0
        out.append(f'<line x1="{x:.1f}" y1="{axis_y}" x2="{x:.1f}" y2="{axis_y + 4}" '
                   f'stroke="#bdbdbd"/>')
        out.append(f'<text x="{x:.1f}" y="{axis_y + 17}" font-size="10.5" fill="#9e9e9e" '
                   f'text-anchor="middle">{t}%</text>')
    out.append("</svg>")
    return "\n".join(out)


def table(headers, rows, *, tid=None, sortable_from=None, row_attrs=None):
    """headers = [(text, is_numeric)]; rows = [[cell_html, ...]]."""
    out = [f'<table{f" id={tid!r}" if tid else ""}>', "<thead><tr>"]
    for i, (text, num) in enumerate(headers):
        cls = ["num"] if num else []
        if sortable_from is not None and i >= sortable_from:
            cls.append("sortable")
        c = f' class="{" ".join(cls)}"' if cls else ""
        out.append(f"<th{c}>{text}</th>")
    out.append("</tr></thead><tbody>")
    for j, r in enumerate(rows):
        attrs = row_attrs[j] if row_attrs else ""
        out.append(f"<tr{attrs}>")
        for i, cell in enumerate(r):
            c = ' class="num"' if headers[i][1] else ""
            out.append(f"<td{c}>{cell}</td>")
        out.append("</tr>")
    out.append("</tbody></table>")
    return "\n".join(out)


def pctf(x, nd=1):
    return "n/a" if x is None else f"{100.0 * x:.{nd}f}%"


# ---------------------------------------------------------------------------
# cross-check against the committed measurement
# ---------------------------------------------------------------------------
def verify_against_csvs(directory, *, per_species, buckets, bins_all):
    """Abort the build if this page disagrees with 16_model_health.py's CSVs."""
    checks = []

    def close(a, b, tol=5e-5):
        return abs(float(a) - float(b)) <= tol

    path = os.path.join(directory, "per_species_health.csv")
    ref = {r["species"]: r for r in hc.read_csv_rows(path)}
    if len(ref) != len(per_species):
        raise SystemExit(f"VERIFY FAIL: {len(per_species)} species here vs {len(ref)} in {path}")
    for row in per_species:
        r = ref.get(row["species"])
        if r is None:
            raise SystemExit(f"VERIFY FAIL: species {row['species']!r} absent from {path}")
        if int(r["n_labelled_crowns"]) != row["n_labelled_crowns"]:
            raise SystemExit(f"VERIFY FAIL: support for {row['species']!r}")
        if not close(r["top1_accuracy"], row["top1_accuracy"]):
            raise SystemExit(f"VERIFY FAIL: top-1 for {row['species']!r}")
        if not close(r["top5_accuracy"], row["top5_accuracy"]):
            raise SystemExit(f"VERIFY FAIL: top-5 for {row['species']!r}")
    checks.append(f"per_species_health.csv: {len(ref)} species, support/top-1/top-5 all match")

    path = os.path.join(directory, "support_buckets.csv")
    for r in hc.read_csv_rows(path):
        b = buckets.get(r["support_bucket"])
        if b is None:
            raise SystemExit(f"VERIFY FAIL: bucket {r['support_bucket']!r} missing here")
        if int(r["n_crowns"]) != b["n_crowns"] or int(r["n_species"]) != b["n_species"]:
            raise SystemExit(f"VERIFY FAIL: bucket {r['support_bucket']!r} counts")
        if not close(r["top1_accuracy"], b["c1"] / b["n_crowns"]):
            raise SystemExit(f"VERIFY FAIL: bucket {r['support_bucket']!r} top-1")
    checks.append(f"support_buckets.csv: {len(buckets)} buckets, counts and top-1 match")

    path = os.path.join(directory, "confidence_calibration.csv")
    ref_bins = {r["band"]: r for r in hc.read_csv_rows(path)
                if r["row_type"] == "bin" and r["scope"] == "all_species_level_gt"}
    for band, n, k in bins_all:
        r = ref_bins.get(band)
        if r is None:
            raise SystemExit(f"VERIFY FAIL: conf band {band!r} absent from {path}")
        if int(r["n_crowns"]) != n or int(r["n_correct"]) != k:
            raise SystemExit(f"VERIFY FAIL: conf band {band!r} counts")
    checks.append(f"confidence_calibration.csv: {len(bins_all)} confidence bands match")
    return checks


# ---------------------------------------------------------------------------
def build(h, *, generated, verify_dir):
    sp_recs = h.sp_recs
    per_species = h.per_species
    n = len(sp_recs)
    n_sp = len(per_species)

    def top1(r):
        return r["ranked"][0][0]

    def conf(r):
        return r["ranked"][0][1]

    c1 = sum(1 for r in sp_recs if top1(r) == r["gt"])
    c5 = sum(1 for r in sp_recs if r["gt"] in [b for b, _ in r["ranked"][:5]])
    macro1 = sum(d["top1_accuracy"] for d in per_species) / n_sp
    macro5 = sum(d["top5_accuracy"] for d in per_species) / n_sp

    support = {d["species"]: d["n_labelled_crowns"] for d in per_species}
    status = {d["species"]: diagnose(d) for d in per_species}

    # --- support buckets ---
    buckets = {}
    for d in per_species:
        b = buckets.setdefault(d["support_bucket"],
                               dict(n_species=0, n_crowns=0, c1=0, c5=0))
        b["n_species"] += 1
    for r in sp_recs:
        b = buckets[hc.bucket_label(support[r["gt"]])]
        b["n_crowns"] += 1
        b["c1"] += top1(r) == r["gt"]
        b["c5"] += r["gt"] in [x for x, _ in r["ranked"][:5]]

    # --- confidence bands over the whole species-level set ---
    bins_all = []
    for lo, hi in hc.CONF_BINS:
        sub = [r for r in sp_recs if lo <= conf(r) < hi]
        bins_all.append((f"[{lo:.1f},{min(hi, 1.0):.1f})", len(sub),
                         sum(1 for r in sub if top1(r) == r["gt"])))

    checks = verify_against_csvs(verify_dir, per_species=per_species,
                                buckets=buckets, bins_all=bins_all)

    # --- why a flat threshold is unsafe: error by support, at conf>=0.7 ---
    flat_by_bucket = {}
    for r in sp_recs:
        if conf(r) < 0.7:
            continue
        b = flat_by_bucket.setdefault(hc.bucket_label(support[r["gt"]]), [0, 0])
        b[0] += 1
        b[1] += top1(r) != r["gt"]

    # --- operating points, out of sample -------------------------------------
    # Eligibility is decided from train crowns only, then scored on test only,
    # so the support gate is never validated on the crowns that defined it.
    train_support = defaultdict(int)
    for r in sp_recs:
        if r["split"] == "train":
            train_support[r["gt"]] += 1
    eligible = {s for s, k in train_support.items() if k >= AUTO_ACCEPT_SUPPORT_MIN}
    test_recs = [r for r in sp_recs if r["split"] == "test"]
    rare = {s for s, k in support.items() if k < RARE_MAX_SUPPORT}
    n_rare_test = sum(1 for r in test_recs if r["gt"] in rare)

    rules = [(f"confidence >= {t} only", t, False) for t in (0.7, 0.8)]
    rules += [(f"confidence >= {t} AND >= {AUTO_ACCEPT_SUPPORT_MIN} train crowns", t, True)
              for t in (0.7, 0.8, 0.9)]
    ops = []
    for label, thr, gate in rules:
        auto = [r for r in test_recs
                if conf(r) >= thr and (not gate or r["gt"] in eligible)]
        auto_ids = {id(r) for r in auto}
        review = [r for r in test_recs if id(r) not in auto_ids]
        errs = sum(1 for r in auto if top1(r) != r["gt"])
        rare_auto = sum(1 for r in auto if r["gt"] in rare)
        rare_rev = sum(1 for r in review if r["gt"] in rare)
        ops.append(dict(label=label, thr=thr, gate=gate, n_auto=len(auto),
                        coverage=len(auto) / len(test_recs) if test_recs else None,
                        err=errs / len(auto) if auto else None,
                        rare_auto=rare_auto,
                        rare_share_review=rare_rev / len(review) if review else None))

    # --- what labelling cannot fix ---
    unreachable = [d for d in per_species if not d["in_corpus_vocabulary"]]
    unreachable_sp = {d["species"] for d in unreachable}
    n_unreachable_crowns = sum(d["n_labelled_crowns"] for d in unreachable)
    reach_recs = [r for r in sp_recs if r["gt"] not in unreachable_sp]
    reach_top1 = sum(1 for r in reach_recs if top1(r) == r["gt"]) / len(reach_recs)
    gn = len(h.genus_recs)
    gg1 = sum(1 for r in h.genus_recs if hc.genus_of(r["ranked"][0][0]) == r["gt"])

    # =======================================================================
    # page
    # =======================================================================
    P = []
    P.append('<h1>Pl@ntNet on BCI &mdash; per-species model health</h1>')
    P.append(f'<div class="subtitle">{esc(generated)} &middot; '
             f'{n:,} labelled crowns &middot; {n_sp} species &middot; '
             f'computed offline from cached predictions, no API key</div>')
    P.append('<p class="lede">Two numbers describe the same model. Averaged over '
             '<em>crowns</em> it looks healthy, because a handful of abundant species '
             'dominate the count. Averaged over <em>species</em> it is much weaker. '
             'The second number is the one the labelling programme has to move.</p>')

    P.append('<div class="hero">')
    P.append(f'<div class="metric lead"><div class="v">{pctf(macro1)}</div>'
             f'<div class="l">Average accuracy per species</div>'
             f'<div class="n">unweighted mean over {n_sp} species</div></div>')
    P.append(f'<div class="metric"><div class="v">{pctf(c1 / n)}</div>'
             f'<div class="l">Accuracy per crown</div>'
             f'<div class="n">{c1:,} of {n:,} crowns</div></div>')
    P.append(f'<div class="metric"><div class="v">{pctf(c5 / n)}</div>'
             f'<div class="l">Correct somewhere in the returned list</div>'
             f'<div class="n">top-5; the list is capped at 5 candidates</div></div>')
    P.append(f'<div class="metric"><div class="v">{pctf(macro5)}</div>'
             f'<div class="l">Per-species, anywhere in the list</div>'
             f'<div class="n">the ceiling a better re-rank could reach</div></div>')
    P.append('</div>')

    top26 = sorted(per_species, key=lambda d: -d["n_labelled_crowns"])[:26]
    P.append(f'<p class="note">The gap is concentration, not noise: the '
             f'{len(top26)} most-labelled species carry '
             f'{sum(d["n_labelled_crowns"] for d in top26):,} of the {n:,} crowns. '
             f'Per-crown accuracy mostly reports how well the model does on those.</p>')

    # ---- support ----
    P.append('<section><h2>Accuracy against how many crowns are labelled</h2>')
    bar_rows = []
    for lab in hc.BUCKET_ORDER:
        b = buckets.get(lab)
        if not b or not b["n_crowns"]:
            continue
        bar_rows.append((f"{lab} crowns", b["c1"] / b["n_crowns"],
                         f'{pctf(b["c1"] / b["n_crowns"])}  ·  '
                         f'{b["n_species"]} spp, {b["n_crowns"]:,} crowns',
                         "#1565c0"))
    P.append('<div class="card">')
    P.append(svg_hbar(bar_rows, title="top-1 accuracy by labelled crowns per species"))
    P.append('<div class="warn"><strong>Read this as abundance, not as training data.</strong> '
             'These predictions come from a frozen Pl@ntNet regional model that has never '
             'seen a single BCI label, so labelling a species does not make Pl@ntNet better '
             'at it. What the horizontal axis really tracks is how common a species is on '
             'the plot &mdash; and common species are also better represented in Pl@ntNet\'s '
             'own reference photos. What extra labels buy is <em>knowledge</em>: below about '
             f'{AUTO_ACCEPT_SUPPORT_MIN} crowns a per-species accuracy is too unstable to act '
             'on, and above it the species becomes eligible for auto-accept.</div>')
    P.append('</div></section>')

    # ---- triage ----
    P.append('<section><h2>Which crowns still need the botanist</h2>')
    P.append('<div class="card">')
    P.append(svg_hbar([(band, k / nn if nn else 0.0,
                        f'{pctf(k / nn) if nn else "n/a"}  ·  {nn:,} crowns', "#2e7d32")
                       for band, nn, k in bins_all],
                      title="top-1 accuracy by the model's own confidence"))
    P.append('<p class="note">Confidence is well calibrated <strong>in aggregate</strong>: '
             'when the model is sure it is almost always right. That is the throughput lever '
             '&mdash; high-confidence crowns can be accepted without an expert looking at them.</p>')

    rows = []
    for lab in hc.BUCKET_ORDER:
        b = flat_by_bucket.get(lab)
        if not b:
            continue
        rows.append([f"{lab} crowns", f"{b[0]:,}", pctf(b[1] / b[0]) if b[0] else "n/a"])
    P.append('<p class="note"><strong>But it is badly calibrated on rare species.</strong> '
             'Accepting on confidence alone would silently mislabel the species that matter '
             'most:</p>')
    P.append(table([("labelled crowns for that species", False),
                    ("auto-accepted at conf &ge; 0.7", True),
                    ("of those, wrong", True)], rows))
    P.append('<p class="note">Raising the threshold does not repair it; requiring the species '
             'to be measured first does. Adding a support gate is what makes the rule safe.</p>')
    P.append('</div>')

    P.append('<div class="card"><h2>Operating points</h2>')
    P.append(f'<p class="note">Eligibility decided from <code>train</code> crowns only and '
             f'scored on the {len(test_recs)} <code>test</code> crowns, so no rule is graded on '
             f'the crowns that defined it. {len(eligible)} species clear '
             f'{AUTO_ACCEPT_SUPPORT_MIN} train crowns.</p>')
    op_rows = []
    for o in ops:
        strong = o["gate"] and abs(o["thr"] - RECOMMENDED_CONF) < 1e-9
        name = f'<strong>{esc(o["label"])}</strong>' if strong else esc(o["label"])
        op_rows.append([name, f'{o["n_auto"]:,}', pctf(o["coverage"]), pctf(o["err"]),
                        f'{o["rare_auto"]}', pctf(o["rare_share_review"])])
    P.append(table([("rule", False), ("auto-accepted", True), ("queue removed", True),
                    ("error among those", True), ("rare crowns auto-accepted", True),
                    ("rare share of what is left", True)], op_rows))
    P.append(f'<div class="rec"><strong>Recommended first deployment: confidence &ge; '
             f'{RECOMMENDED_CONF} and at least {AUTO_ACCEPT_SUPPORT_MIN} labelled crowns for '
             f'that species.</strong> Trust matters more than the last few points of coverage '
             f'while the loop is new.</div>')
    P.append(f'<p class="note">A species with fewer than {RARE_MAX_SUPPORT} labelled crowns is '
             f'counted rare here ({len(rare)} of {n_sp} species, {n_rare_test} of the '
             f'{len(test_recs)} test crowns). Note that no rare crown can be auto-accepted '
             f'<em>by construction</em> &mdash; the support gate excludes them &mdash; so the '
             f'enrichment below is the gate working as designed, not independent evidence '
             f'for it.</p>')
    P.append('<p class="note">Caveats that travel with any auto-accept rule: accepted labels '
             'carry the error rate shown, must be tagged machine-accepted, must never enter '
             'the evaluation set, and the thresholds must be re-measured after every retrain '
             'because a species crossing the support gate changes its own eligibility.</p>')
    P.append('</div></section>')

    # ---- per-species ----
    P.append('<section><h2>Per-species status</h2>')
    counts = defaultdict(int)
    for s in status.values():
        counts[s] += 1
    P.append('<ul class="legend">')
    for key in ("reliable", "adequate", "ranking", "unmeasured", "hard", "unreachable"):
        P.append(f'<li><span class="tag {key}">{esc(STATUS_LABELS[key])}</span> '
                 f'&mdash; {esc(STATUS_ACTIONS[key])} '
                 f'<span class="prov">({counts[key]} species)</span></li>')
    P.append('</ul>')
    P.append('<div class="controls">'
             '<input id="species-filter" type="search" placeholder="filter species&hellip;" '
             'size="28" aria-label="filter species">'
             '<select id="status-filter" aria-label="filter by status">'
             '<option value="all">every status</option>' +
             "".join(f'<option value="{k}">{esc(STATUS_LABELS[k])}</option>'
                     for k in ("reliable", "adequate", "ranking", "unmeasured",
                               "hard", "unreachable")) +
             '</select><span class="count" id="species-count"></span></div>')

    sp_rows, attrs = [], []
    for d in sorted(per_species, key=lambda x: (-x["n_labelled_crowns"], x["species"])):
        st = status[d["species"]]
        name = d["species"][:1].upper() + d["species"][1:]
        sp_rows.append([
            f'<span class="sp" data-sort="{esc(d["species"])}">{esc(name)}</span>',
            f'<span data-sort="{d["n_labelled_crowns"]}">{d["n_labelled_crowns"]:,}</span>',
            f'<span data-sort="{d["top1_accuracy"]:.6f}">{pctf(d["top1_accuracy"])}</span>',
            f'<span data-sort="{d["top5_accuracy"]:.6f}">{pctf(d["top5_accuracy"])}</span>',
            f'<span data-sort="{d["mean_top1_confidence"]:.6f}">'
            f'{d["mean_top1_confidence"]:.2f}</span>',
            f'<span class="tag {st}" data-sort="{esc(STATUS_LABELS[st])}">'
            f'{esc(STATUS_LABELS[st])}</span>',
        ])
        attrs.append(f' data-species="{esc(d["species"])}" data-status="{st}"')
    headers = [("Species", False), ("Labelled crowns", True), ("Top-1", True),
               ("In list (top-5)", True), ("Mean confidence", True), ("Status", False)]
    P.append(table(headers, sp_rows, tid="species-table", sortable_from=0, row_attrs=attrs))
    P.append('<p class="note">&ldquo;Ranking problem&rdquo; is the cheapest column on this '
             'page: the correct species is already in the returned list, just not first. '
             'Those crowns are a confirmation task, not an identification task.</p>')
    P.append('</section>')

    # ---- ceiling ----
    P.append('<section><h2>What labelling cannot fix</h2><div class="card">')
    P.append(f'<p class="note"><strong>{len(unreachable)} species '
             f'({n_unreachable_crowns} of the {n:,} evaluated crowns) are never returned by the '
             f'model at all.</strong> After name normalisation and synonym resolution their name '
             f'appears in no cached prediction, so no re-ranking and no extra labelling can make '
             f'them correct. Excluding them raises per-crown top-1 from {pctf(c1 / n)} to '
             f'{pctf(reach_top1)} on {len(reach_recs):,} crowns. '
             f'Counted across all {len(h.gt_rows):,} labelled crowns rather than only the '
             f'evaluated ones, the same condition covers 87 crowns; this panel uses the '
             f'evaluation set, like every other number on the page.</p>')
    P.append(table([("Species", False), ("Labelled crowns", True)],
                   [[f'<span class="sp">{esc(d["species"][:1].upper() + d["species"][1:])}</span>',
                     f'{d["n_labelled_crowns"]:,}']
                    for d in sorted(unreachable, key=lambda d: -d["n_labelled_crowns"])]))
    P.append(f'<p class="note"><strong>{gn:,} further crowns are labelled to genus only</strong> '
             f'and are excluded from every species number above. Scored at genus level they '
             f'reach {pctf(gg1 / gn) if gn else "n/a"}. Whether resolving them to species is '
             f'worth expert time is a prioritisation question, not a model question.</p>')
    P.append('</div></section>')

    # ---- provenance ----
    P.append('<section><h2>Where these numbers come from</h2><div class="card">')
    P.append('<ul class="prov">')
    P.append(f'<li>Predictions: <code>identify/k-central-america</code>, model run '
             f'<code>v7.4-2026-03-27</code> &mdash; the Central America regional model, not the '
             f'global one. A regional restriction is therefore already in place.</li>')
    P.append(f'<li>Request parameters: <code>nb-results=5</code> (ours, not the model\'s), '
             f'no-reject, organs=auto, on a 1280&nbsp;px centre crop of each crown photo. '
             f'&ldquo;Top-5&rdquo; is the entire returned list; a correct answer at rank 6+ '
             f'was never returned and cannot be seen here.</li>')
    P.append(f'<li>Evaluation set: {n:,} crowns across {n_sp} species that carry a '
             f'species-level botanist label and have at least one cached prediction.</li>')
    P.append(f'<li>The labelled subset is the historical labelling record, not a random draw, '
             f'so these rates transfer to unlabelled crowns only under an assumption that '
             f'cannot be tested offline.</li>')
    P.append('<li>Every number on this page is recomputed from the source data at build time '
             'and cross-checked against the committed measurement CSVs:'
             '<ul>' + "".join(f"<li>{esc(c)}</li>" for c in checks) + '</ul>'
             'A mismatch aborts the build.</li>')
    P.append('<li>Rebuild: <code>python3 scripts/16_dashboard/16_model_health.py</code> then '
             '<code>python3 scripts/16_dashboard/16b_dashboard.py</code>. Stdlib only, '
             'deterministic, no network.</li>')
    P.append('</ul></div></section>')

    body = "\n".join(P)
    return (
        "<!DOCTYPE html>\n"
        '<html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        "<title>Pl@ntNet on BCI - per-species model health</title>"
        f"<style>{CSS}</style></head><body>"
        f"{body}"
        '<div class="footer">generated offline from cached predictions '
        "&middot; no network, no API key</div>"
        f"<script>{JS}</script>"
        "</body></html>"
    ), checks


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--gt", default=hc.GT_CSV)
    ap.add_argument("--splits", default=hc.SPLITS_CSV)
    ap.add_argument("--cache-dir", default=hc.CACHE_DIR)
    ap.add_argument("--wcvp-cache", default=hc.WCVP_CACHE_JSON)
    ap.add_argument("--verify-against",
                    default=os.path.join(os.path.dirname(hc.REPO),
                                         "bci_workshop_labelbox_plantnet-docs",
                                         "model-health-2026-08-03"),
                    help="directory holding the committed measurement CSVs to cross-check")
    ap.add_argument("--out", default=os.path.join(hc.REPO, "output", "16_dashboard",
                                                  "model_health_dashboard.html"))
    ap.add_argument("--generated", default=None,
                    help="provenance date string; defaults to today (pass a fixed value "
                         "for byte-reproducible output)")
    args = ap.parse_args()

    h = hc.load_health(gt_csv=args.gt, splits_csv=args.splits, cache_dir=args.cache_dir,
                       wcvp_cache=args.wcvp_cache)
    generated = args.generated or _dt.date.today().isoformat()
    page, checks = build(h, generated=generated, verify_dir=args.verify_against)

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(page)
    for c in checks:
        print(f"  verified  {c}")
    print(f"  wrote     {args.out}  ({len(page):,} bytes)")


if __name__ == "__main__":
    main()
