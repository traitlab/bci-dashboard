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

from collections import Counter

import health_core as hc
from dashboard_assets import esc, panel, pctf, svg_hbar, svg_weight_pair

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


def candidates_panel(*, recs, gen_n, gen_none):
    """Where the five-candidate limit comes from, and what it hides.

    ``recs`` is every crown that got a prediction, species-level or not, so the
    list-length picture covers the same photos the rest of the page scores.
    """
    lens = Counter(len(r["ranked"]) for r in recs)
    top = max(lens)
    full = lens[top]
    rows = [(f"{k} guess{'' if k == 1 else 'es'}", lens[k] / len(recs),
             f"{lens[k]:,} crowns", "#1b5e20" if k == top else "#78909c")
            for k in range(1, top + 1) if lens[k]]
    return panel(
        f"Why only {top} guesses per photo, and what that hides",
        f"<b>We asked for {top}. Pl@ntNet did not stop at {top} on its own.</b> That choice "
        f"puts a ceiling on every number above it, so it is worth knowing where it came from.",
        f'<p class="note">Every time we sent Pl@ntNet a photo we added one instruction: '
        f'<em>reply with your {top} best guesses, best first</em>. In the request that is the '
        f'setting <code>nb-results={top}</code>. Pl@ntNet\'s own documentation calls it a way '
        f'to "restrict size of output list of probable species", says only that it takes "an '
        f'integer &gt;= 1", and adds that "fewer results improve response time". So there is '
        f'no published maximum and no published default: the ceiling on a longer request is '
        f'however many candidates the model itself has for the photo. The number {top} lives '
        f'in one line of <code>config.yaml</code> '
        f'(<code>identify_nb_results: {top}</code>), carried over from the Amazon pipeline this '
        f'project was built from, with no recorded reason and long before any of the accuracy '
        f'on this page had been measured. It is a setting to revisit rather than a fact about '
        f'the model.</p>'
        + svg_hbar(rows, title=f"how long the returned list actually was, {len(recs):,} crowns")
        + f'<p class="note">{full:,} of {len(recs):,} photos came back with a full {top} '
          f'({pctf(full / len(recs))}), and none came back with more, which is the limit doing '
          f'its work. The shorter lists are Pl@ntNet returning fewer than we asked for, so '
          f'those are its ceiling rather than ours.</p>'
          f'<p class="note"><b>What it hides: a right answer sitting in position '
          f'{top + 1}.</b> If the correct species was Pl@ntNet\'s next guess after the ones we '
          f'asked for, this page cannot tell that apart from Pl@ntNet never having heard of the '
          f'plant. Both look like a miss. The clearest sign of it is among the {gen_n:,} crowns '
          f'whose botanist label stops at the genus: {gen_none:,} of them have no species from '
          f'that genus anywhere in the {top}, and for a genus the model plainly knows, some of '
          f'those are very likely sitting just below the cut.</p>'
          f'<p class="note">Raising it is not free. These answers are cached, so rebuilding '
          f'this page costs nothing, but a longer list means asking Pl@ntNet again for every '
          f'photo in the collection at one paid call each. That is a decision to take, not a '
          f'rebuild to run.</p>'
          f'<p class="note"><b>If that call is ever made, ask for more than a longer list.</b> '
          f'The same endpoint takes <code>detailed=true</code>, which the documentation says '
          f'returns "extra identification results such as results per family and results per '
          f'genus" under <code>otherResults</code>. Those are exactly the answers this page has '
          f'to fake today: a genus label is scored by chopping the genus off a predicted '
          f'species name, and a family label cannot be scored offline at all. Pl@ntNet will '
          f'state both directly if asked.</p>')


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
            f'<li>Request settings: <code>nb-results=5</code>, sent explicitly on every '
            f'request from <code>config.yaml</code> <code>identify_nb_results</code> and not '
            f'an API default, plus <code>no-reject=true</code>, organs detected '
            f'automatically, and <code>include-related-images=false</code>, on a '
            f'1280&nbsp;px centre crop of each crown photo. A correct answer at position 6 '
            f'or beyond was never returned and cannot be seen here.</li>'
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
