"""The queue page's measured evidence for its own ordering.

Two files ``labelling/rank_queue.py`` writes on request, outside
``bin/refresh.sh``, and this module reads with the standard library only:

- ``selection_audit.json``: on the photos that already carry a name, does this
  order find rare species faster than a random one, over several random
  starts, and is the difference more than chance.
- ``selection_confound.json``: does "looks unlike the labelled photos" still
  track a rarely-labelled species once the site, the flight, or the export
  batch, is held fixed. Four tests: the labelled photos by site, the queue by
  export batch, the queue by site, the queue by flight (one date at one site).
  A photo whose site could not be read is left out of the site and flight
  tests, and each test says how many.

Both are labelfirst's own tests, run on this checkout's photos. The page never
quotes a number from a paper for a different model: the only gain it prints is
the one measured here, with the population and the count beside it.

An absent file is the normal state of a fresh clone and the panel says so. A
file that disagrees with the ordering it is meant to describe is a build
failure, the same way a missing ordering file is: ``selection_complaint`` names
the file, and ``build_internal`` refuses.
"""

from __future__ import annotations

import json
import os

import core as hc
from assets import esc, more

# The covariates the ranker tests, in the plural the page needs for a count.
COUNT_WORDS = {1: "once", 2: "twice", 3: "three times", 4: "four times",
               5: "five times", 6: "six times"}

PLURAL = {"site": "sites", "export batch": "export batches", "flight": "flights"}
# How many hex digits of a file hash the page prints: enough to tell two files
# apart, short enough to read against the ordering file's own record.
SHA_SHOWN = 12
# How labelfirst names each verdict, and what the page says instead.
VERDICT_WORDS = {
    "robust": "holds once the {cov} is held fixed",
    "confounded": "is mostly the {cov}, and fades once it is held fixed",
    "mixed": "is partly the {cov}",
    "no-signal": "is not there either way",
}


def _read(path: str):
    """The parsed file, or ``None`` when it is not there. A file that is there
    and is not JSON is a fault, not an absence, and is named."""
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        try:
            return json.load(f)
        except ValueError as e:
            raise SystemExit(f"{path} is not JSON: {e}") from None


def _num(v):
    """A number as a float, anything else as ``None``: a missing number is
    reported as missing, never as zero."""
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def selection_audit(path: str | None = None) -> dict | None:
    """The audit file, flattened to what the page prints. ``None`` when absent.

    ``passed`` is labelfirst's own rule read back off the numbers it wrote: the
    low end of the range is above zero and the paired test clears half the
    alpha, since the test is one-sided on a two-sided alpha.
    """
    d = _read(path or hc.SELECTION_AUDIT_JSON)
    if d is None:
        return None
    a = d.get("audit") or {}
    h1 = a.get("h1_sustainability") or {}
    eff = d.get("efficiency") or {}
    pre = d.get("preflight") or {}
    other = d.get("separability_other_flight") or {}
    pop = d.get("population") or {}
    prm = d.get("params") or {}
    run = d.get("run") or {}
    out = {
        "gain": _num(h1.get("pct_gain")), "ci_low": _num(h1.get("ci_low")),
        "ci_high": _num(h1.get("ci_high")), "p": _num(h1.get("wilcoxon_p")),
        "alpha": _num(a.get("alpha")), "n_seeds": a.get("n_seeds"),
        "rounds": a.get("rounds"), "k_per_round": prm.get("k_per_round"),
        "seed_pool": prm.get("seed_pool_size"),
        "n_frames": pop.get("n_frames"), "n_species": pop.get("n_species"),
        "n_rare": pop.get("n_rare_species"), "rare_threshold": pop.get("rare_threshold"),
        "labels_saved_pct": _num(eff.get("labels_saved_pct")),
        "rounds_to_match": _num(eff.get("challenger_rounds_to_match")),
        "baseline_rounds": eff.get("baseline_rounds"),
        "separability_pct": _num(pre.get("separability_pct")),
        "on_ladder": pre.get("gain_on_ladder"),
        "separability_other_flight_pct": _num(other.get("pct_other_flight")),
        "separability_unplaced": other.get("n_unreconciled"),
        "library": a.get("library_version"), "sha": a.get("embedding_sha256"),
        "n_seeds_agreeing": a.get("n_seeds_agreeing"),
        "written": (run.get("extra") or {}).get("written"),
    }
    out["passed"] = (out["ci_low"] is not None and out["p"] is not None
                     and out["alpha"] is not None
                     and out["ci_low"] > 0 and out["p"] < out["alpha"] / 2)
    return out


def selection_confound(path: str | None = None) -> dict | None:
    """The confound file: one entry per test, plus the hash of the pool it was
    run against. ``None`` when absent."""
    d = _read(path or hc.SELECTION_CONFOUND_JSON)
    if d is None:
        return None
    tests = []
    for t in d.get("audits") or []:
        tests.append({
            "population": t.get("population"), "covariate": t.get("covariate"),
            "verdict": t.get("verdict"), "raw": _num(t.get("raw_corr")),
            "partial": _num(t.get("partial_corr")), "p": _num(t.get("partial_p")),
            "eta2": _num(t.get("covariate_eta2")), "n": t.get("n"),
            "n_groups": t.get("n_groups"), "n_unreconciled": t.get("n_unreconciled")})
    run = d.get("run") or {}
    return {"tests": tests, "sha": run.get("embedding_sha256"),
            "anchor_sha": (run.get("extra") or {}).get("anchor_sha256"),
            "library": run.get("library_version"),
            "written": (run.get("extra") or {}).get("written")}


def selection_complaint(audit: dict | None, confound: dict | None,
                        provenance: dict) -> str:
    """Why a page must not be built off these files, or ``""``.

    Each file records the hash of the file of photo vectors it was run on. The
    ordering file records the same. When they disagree the evidence panel would
    be describing a different pool, or a different set of labelled photos, from
    the one the queue was ordered against. That is stale evidence under a fresh
    order, and a reader cannot tell. Absent files are not stale: the panel says
    they are missing. A hash the ordering file does not carry (the older text
    sidecar) cannot be checked, and is let through with the panel's own caveat.
    """
    def stale(name, got, want, what):
        return (f"{name} was run on {what} {got[:12]}, but the ordering file was "
                f"built against {want[:12]}. Re-run labelling/rank_queue.py "
                f"{'--audit' if 'audit' in name else '--confound'}, or remove the file.")
    if audit and audit.get("sha") and provenance.get("anchor_sha") \
            and audit["sha"] != provenance["anchor_sha"]:
        return stale(hc.SELECTION_AUDIT_JSON, audit["sha"], provenance["anchor_sha"],
                     "labelled photos")
    if confound and confound.get("sha") and provenance.get("sha") \
            and confound["sha"] != provenance["sha"]:
        return stale(hc.SELECTION_CONFOUND_JSON, confound["sha"], provenance["sha"],
                     "a pool")
    return ""


def _pct(x, nd=0) -> str:
    return "n/a" if x is None else f"{x:.{nd}f}%"


def _p(x) -> str:
    if x is None:
        return "n/a"
    return "under 0.001" if x < 0.001 else f"{x:.3f}"


NOT_AUDITED = (
    '<p class="note"><b>Not yet measured against a random order on this checkout.</b> '
    '<code>labelling/rank_queue.py --audit</code> writes that comparison, and this '
    'panel prints it when the file is there.</p>')

NOT_CONFOUNDED = (
    '<p class="note"><b>Not yet tested against the site, the flight and the export batch '
    'on this checkout.</b> <code>labelling/rank_queue.py --confound</code> writes that test, '
    'and this panel prints it when the file is there.</p>')


def audit_note(c) -> str:
    """Does this order find rare species faster than a random one. The number,
    its range, how many random starts it rests on, and what it was measured on."""
    a = getattr(c, "selection_audit", None)
    if not a:
        return NOT_AUDITED
    n = a.get("n_frames") or 0
    claim = (f'this order found {_pct(a["gain"])} more rare species over the run than a '
             f'random order did, range {_pct(a["ci_low"])} to {_pct(a["ci_high"])}, '
             f'p {_p(a["p"])}.'
             if a["passed"] else
             f'the difference from a random order ({_pct(a["gain"])}, range '
             f'{_pct(a["ci_low"])} to {_pct(a["ci_high"])}, p {_p(a["p"])}) is not more '
             f'than chance gives at {a["n_seeds"]} starts, so the page claims nothing '
             f'from it.')
    agree = ""
    if a["n_seeds_agreeing"] is not None:
        agree = (f' {a["n_seeds_agreeing"]} of {a["n_seeds"]} starts favoured this order '
                 f'over the random one.')
    saved = ""
    if a["passed"] and a["rounds_to_match"] is not None and a["baseline_rounds"]:
        saved = (f' It reached in {a["rounds_to_match"]:.0f} rounds what the random order '
                 f'reached in {a["baseline_rounds"]}: {_pct(a["labels_saved_pct"])} '
                 f'fewer labels for the same rare species.')
    ladder = ""
    if a["separability_pct"] is not None:
        where = ("inside" if a["on_ladder"] else "outside")
        ladder = (f' A separate check: {_pct(a["separability_pct"])} of these photos '
                  f'have a same-species nearest photo as the model sees them.')
        # Photos from one flight overlap, so that nearest photo can be a
        # near-copy. The rate with it drawn from another flight is measured,
        # not assumed; an audit written before it was measured says so.
        if a["separability_other_flight_pct"] is not None:
            ladder += (f' When that photo must come from another flight, meaning '
                       f'another date or another site, it is '
                       f'{_pct(a["separability_other_flight_pct"])}.')
            if a["separability_unplaced"]:
                ladder += (f' {a["separability_unplaced"]:,} photos with no readable '
                           f'flight are left out of that second rate.')
        else:
            ladder += (' Photos from one flight overlap, and this audit does not say '
                       'how much of that rate rests on them.')
        ladder += (f' The first rate is '
                   f'{where} the range where labelfirst can predict a gain in advance, so '
                   f'the number above is a measurement with no prediction beside it.')
    # The answer and what it was measured on stay open. The shape of a run, the
    # labels it saves, the separability check and the provenance are what a
    # reader checking the answer asks for next, and they wait behind a summary.
    return (f'<p class="note"><b>Does this order find rare species faster than a random '
            f'one?</b> Measured on the {n:,} photos that already carry a name: '
            f'{a["n_species"] or 0:,} species, {a["n_rare"] or 0:,} of them rare, meaning '
            f'{a["rare_threshold"]} or fewer labelled frames. Over {a["n_seeds"]} random '
            f'starts, {claim}{agree}</p>'
            + more("How the runs were set up, and what they rest on",
                   f'<p class="note">Each run starts from {a["seed_pool"]} photos picked '
                   f'at random and adds {a["k_per_round"]} a round for {a["rounds"]} '
                   f'rounds.{saved}{ladder} Measured with labelfirst '
                   f'{esc(a["library"] or "unknown")} on this checkout, against the file '
                   f'of photo vectors {_sha(a["sha"])}, written '
                   f'{esc(a["written"] or "on an unrecorded date")}. No number here comes '
                   f'from a paper or from a different model.</p>'))


def confound_note(c) -> str:
    """Is a photo new for its species, or new for the batch it came from.

    The two hand-counted shares (how much of the head carries the newer file
    naming, against the whole queue) stay as the raw fact. The measured test
    under them says whether the link between "looks new" and "rarely labelled"
    survives holding the site, the flight, or the export batch, fixed. A test
    that left photos out for having no readable site says how many, so the
    count beside it is never quietly short.
    """
    f = getattr(c, "selection_confound", None)
    head = ""
    if getattr(c, "head_n", 0):
        head = (f'Of the {c.head_n:,} photos it puts first, {_pct(100 * c.head_tele_share)} '
                f'carry the newer file naming, against '
                f'{_pct(100 * c.queue_tele_share)} across the queue: a later batch, not '
                f'another camera. ')
    if not f:
        return (f'<p class="note"><b>What this ordering costs.</b> {head}'
                f'Whether the head leans on that batch has not been tested here.</p>'
                + NOT_CONFOUNDED)
    lines = []
    for t in f["tests"]:
        cov = esc(t["covariate"])
        many = PLURAL.get(t["covariate"], cov + "s")
        words = VERDICT_WORDS.get(t["verdict"] or "", "gave a verdict this page does "
                                  "not know, {cov}").format(cov=cov)
        left_out = ""
        if t["n_unreconciled"]:
            left_out = (f' {t["n_unreconciled"]:,} photos were left out because their '
                        f'site could not be read.')
        lines.append(
            f'<li>On the {esc(t["population"])} ({t["n"] or 0:,}, {t["n_groups"] or 0} '
            f'{many}): the link {words}. Rank correlation {_corr(t["raw"])} before, '
            f'{_corr(t["partial"])} after, p {_p(t["p"])}; the {cov} explains '
            f'{_pct(100 * (t["eta2"] or 0))} of how new a photo looks.{left_out}</li>')
    return (f'<p class="note"><b>Is it the species, or the batch?</b> {head}'
            f'A photo can look new for the batch it came from rather than for what grows '
            f'in it. It was tested {_times(f["tests"])}.</p>'
            f'<ul class="note">{"".join(lines)}</ul>'
            f'<p class="note">On the labelled photos the species is known, and on the '
            f'queue it is the one the model guessed. '
            f'Tested with labelfirst {esc(f["library"] or "unknown")} on '
            f'this checkout, written {esc(f["written"] or "on an unrecorded date")}. The '
            f'file of photo vectors was {_sha(f["sha"])} for the queue and '
            f'{_sha(f["anchor_sha"])} for the labelled photos.</p>')


def _times(tests: list) -> str:
    """How many confound tests ran and what each held fixed, read from the
    file, so the count never drifts from the bullets under it."""
    covs = []
    for t in tests:
        cov = t["covariate"] or "an unnamed covariate"
        if cov not in covs:
            covs.append(cov)
    word = COUNT_WORDS.get(len(tests), f"{len(tests)} times")
    if not covs:
        return word
    held = ["the flight, meaning the date and the site, held fixed" if c == "flight"
            else f"{c} held fixed" for c in covs]
    if len(held) > 1:
        held[-1] = "then " + held[-1]
    return f"{word}: {', '.join(held)}"


def _corr(x) -> str:
    return "n/a" if x is None else f"{x:+.2f}"


def _sha(x) -> str:
    """The first SHA_SHOWN hex of a file hash, or a plain "unrecorded"."""
    return esc(x[:SHA_SHOWN]) if x else "an unrecorded hash"
