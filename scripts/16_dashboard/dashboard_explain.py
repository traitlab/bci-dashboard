#!/usr/bin/env python3
"""Prose panels for the model-health dashboard.

Two panels that are mostly explanation rather than measurement live here, so
16b_dashboard.py stays a page assembler:

- ``weighting_panel`` answers the question the two headline numbers always
  provoke, namely how one model can score 81% and 56% at once.
- ``method_panel`` names the model, the request settings, and the assumption
  that cannot be checked offline.

Every figure either arrives already verified from ``health_core`` or is
recomputed here from the same records. Nothing is hardcoded.
"""

import health_core as hc
from dashboard_assets import esc, panel, pctf, svg_weight_pair

# One colour and one plain-English name per labelled-crown band, shared by both
# bars of the weighting chart so a band is recognisable across them. The ramp
# runs bad to good, all dark enough to carry a white number inside the bar.
BAND_COLOR = {"1": "#b71c1c", "2-4": "#d84315", "5-9": "#8d6e00",
              "10-24": "#558b2f", "25+": "#1b5e20"}
BAND_WORD = {"1": "1 crown", "2-4": "2 to 4 crowns", "5-9": "5 to 9 crowns",
             "10-24": "10 to 24 crowns", "25+": "25 or more crowns"}

# Crowns at or below this many labels are "thin" in the near-miss comparison.
THIN_MAX = 4
FAT_MIN = 25


def _near_miss(recs):
    """Wrong first guesses, and the share whose right answer is still listed."""
    wrong = [r for r in recs if r["ranked"][0][0] != r["gt"]]
    got = sum(1 for r in wrong if r["gt"] in [b for b, _ in r["ranked"][:5]])
    return len(wrong), got / len(wrong) if wrong else 0.0


def weighting_panel(*, per_species, sp_recs, support, buckets, now, n, n_sp):
    """Why the crown-weighted and per-species scores differ, with a picture."""
    rows = []
    for lab in hc.BUCKET_ORDER:
        b = buckets.get(lab)
        if not b or not b["n_crowns"]:
            continue
        rows.append((BAND_WORD[lab], b["n_species"] / n_sp, b["n_crowns"] / n,
                     f'{b["n_species"]} species, {b["n_crowns"]:,} crowns, '
                     f'{pctf(b["c1"] / b["n_crowns"])} right', BAND_COLOR[lab]))
    thin, fat = hc.BUCKET_ORDER[0], hc.BUCKET_ORDER[-1]
    thin_n, thin_in5 = _near_miss([r for r in sp_recs if support[r["gt"]] <= THIN_MAX])
    fat_n, fat_in5 = _near_miss([r for r in sp_recs if support[r["gt"]] >= FAT_MIN])
    well_sp = [d for d in per_species if d["n_labelled_crowns"] >= hc.WELL_SAMPLED_MIN_N]
    well = [r for r in sp_recs if support[r["gt"]] >= hc.WELL_SAMPLED_MIN_N]
    well_micro = sum(1 for r in well if r["ranked"][0][0] == r["gt"]) / len(well)
    well_macro = sum(d["top1_accuracy"] for d in well_sp) / len(well_sp)
    gap = 100 * (now["micro_top1"] - now["macro_top1"])
    big = max(per_species, key=lambda d: d["n_labelled_crowns"])
    singles = buckets[thin]["n_species"]
    thin_sp = sum(buckets[lab]["n_species"] for lab in hc.BUCKET_ORDER[:2]
                  if buckets.get(lab))
    return panel(
        f"Why one score says {pctf(now['micro_top1'])} and the other {pctf(now['macro_top1'])}",
        "<b>Same model, same photos, two ways of averaging.</b> Both numbers are right. "
        "The picture below shows where they part company.",
        svg_weight_pair(rows,
                        label_a=f"one vote per species ({n_sp} votes)",
                        label_b=f"one vote per crown ({n:,} votes)")
        + f'<p class="note">Picture a school with {n_sp} classes, one per species, and {n:,} '
          f'students in total, one per labelled crown. Every student sat the same quiz. '
          f'<b>Count every student</b> and the big classes decide the score: that is the '
          f'crown-weighted {pctf(now["micro_top1"])}. <b>Give each class one score and average '
          f'the {n_sp} of them</b> and a class of one student counts as much as '
          f'<em>{esc(big["species"])}</em> with {big["n_labelled_crowns"]:,}: that is the '
          f'per-species {pctf(now["macro_top1"])}. <b>The per-species score is the one a '
          f'labelling programme exists to move, so it is the one to quote here.</b> Quoting '
          f'{pctf(now["micro_top1"])} is not wrong, it answers a question nobody in this '
          f'project is asking.</p>'
          f'<p class="note">Both bars hold the same {n:,} crowns, sorted into the same five '
          f'groups by how many labelled crowns their species has. Only the counting changes. '
          f'The {singles} species with a single crown fill '
          f'{100 * buckets[thin]["n_species"] / n_sp:.0f}% of the top bar and '
          f'{100 * buckets[thin]["n_crowns"] / n:.0f}% of the bottom one. Now read the scores '
          f'in the key: {pctf(buckets[thin]["c1"] / buckets[thin]["n_crowns"])} right for the '
          f'one-crown group, {pctf(buckets[fat]["c1"] / buckets[fat]["n_crowns"])} for the '
          f'{BAND_WORD[fat]} group. The average that leans on the big groups has to come out '
          f'higher.</p>'
          f'<p class="note">That may feel backwards, since common species sound like the easy '
          f'ones to mix up. The species with many crowns here are big canopy trees, and those '
          f'are also the ones photographed most across the world. Pl@ntNet learned from those '
          f'photos, so it already knows them. Rare in our labels usually means rare in its '
          f'photo collection too.</p>'
          f'<p class="note">The mistakes differ at each end too, which changes what to do '
          f'about them. When the model gets a species with {THIN_MAX} crowns or fewer wrong, '
          f'the right name is still somewhere in its five suggestions {pctf(thin_in5)} of the '
          f'time ({thin_n} wrong guesses). For species with {FAT_MIN} crowns or more it is '
          f'{pctf(fat_in5)} ({fat_n} wrong guesses). So misses on well-known species are '
          f'mostly near misses a botanist can settle from the short list, while misses on rare '
          f'species are mostly the model not knowing the plant at all.</p>'
          f'<p class="note"><b>Set aside the species with fewer than {hc.WELL_SAMPLED_MIN_N} '
          f'crowns and the two scores become {pctf(well_micro)} and {pctf(well_macro)}</b>, '
          f'{100 * (well_micro - well_macro):.0f} points apart instead of {gap:.0f}. Part of '
          f'the low per-species score is real weakness on rare species. Part of it is that a '
          f'species with one crown can only score 0% or 100%, with nothing in between, so '
          f'those {singles} votes are coin flips. Both parts point the same way: the crowns '
          f'worth labelling next belong to the {thin_sp} species sitting at {THIN_MAX} labels '
          f'or fewer.</p>',
        open_=True)


def method_panel(*, tag, n, n_sp, checks):
    """Model, request settings, evaluated set, and the untestable assumption."""
    body = ('<ul class="prov">'
            f'<li>Predictions: <code>identify/k-central-america</code>, model run '
            f'<code>{esc(tag)}</code>. The Central America regional model, not the '
            f'worldwide one, so a regional restriction is already in place.</li>'
            f'<li>Request settings: <code>nb-results=5</code> (our choice, not a model '
            f'limit), no reject option, organs detected automatically, on a 1280&nbsp;px '
            f'centre crop of each crown photo. A correct answer at position 6 or beyond was '
            f'never returned and cannot be seen here.</li>'
            f'<li>Evaluated set: {n:,} crowns across {n_sp} species carrying a botanist '
            f'label that names a species rather than only a genus. They are the historical '
            f'labelling record, not a random draw, so these rates carry over to unlabelled '
            f'crowns only under an assumption that cannot be tested offline.</li>'
            f'<li>Trend: one row per snapshot folder and metric in <code>history.csv</code>, '
            f'appended and never rewritten. Each snapshot\'s model tag is read from its own '
            f'<code>run_log.txt</code>, which records the endpoint and the model run '
            f'name.</li>'
            '<li>Every number here is recomputed from the source data at build time and '
            'cross-checked against the committed measurement files:<ul>'
            + "".join(f"<li>{esc(c)}</li>" for c in checks)
            + '</ul>A mismatch aborts the build.</li>'
            '<li>Rebuild: <code>python3 scripts/16_dashboard/16_model_health.py</code> then '
            '<code>python3 scripts/16_dashboard/16b_dashboard.py</code>. Standard library '
            'only, same output every run, no network.</li></ul>')
    return panel("How this was measured, and what it does not tell you",
                 "<b>Read this before quoting any number outside the team.</b> It names "
                 "the model, the request settings, and the one assumption that cannot be "
                 "checked offline.", body)
