"""
Pl@ntNet-on-BCI model health -- data layer.

Stdlib only (no pandas/numpy). Deterministic. No network calls.

Loads GT + splits + cached Pl@ntNet API responses, joins them, reconciles GT
names against the corpus vocabulary (with an optional local WCVP synonym
crosswalk), builds the evaluable per-crown records and aggregates them to
per-species health. Extracted from compute_model_health.py so the report
script and other consumers (e.g. a dashboard) can share one code path.
"""

from __future__ import annotations

import csv
import json
import os
import re
import unicodedata
from collections import Counter, defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from typing import Optional

# --------------------------------------------------------------------------
# INPUT PATHS
# --------------------------------------------------------------------------
# Every path is derived from the checkout, so a clone runs anywhere. Each one
# takes an environment override for machines that keep the data elsewhere:
#   BCI_DASHBOARD_REPO      checkout root            (default: one level up)
#   BCI_DASHBOARD_DATA      measurement inputs       (default: <repo>/data)
#   BCI_DASHBOARD_SNAPSHOTS dated snapshot store     (default: <repo>/snapshots)
#   BCI_WCVP_CACHE          WCVP resolution cache    (default: <repo>/data/wcvp_cache.json)
REPO = os.environ.get("BCI_DASHBOARD_REPO") or os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))
BASE = os.environ.get("BCI_DASHBOARD_DATA") or os.path.join(REPO, "data")

GT_CSV = os.path.join(BASE, "gt_dominant_taxon.csv")
SPLITS_CSV = os.path.join(BASE, "splits.csv")
CACHE_DIR = os.path.join(BASE, "predictions", "cache")

# Dated model-health-<date>/ folders: the trend history, kept beside the code
# that reads it. Gitignored.
SNAPSHOT_DIR = os.environ.get("BCI_DASHBOARD_SNAPSHOTS") or os.path.join(REPO, "snapshots")

# Local warm WCVP resolution cache (built earlier from the GBIF-hosted WCVP
# dataset f382f0ce-323a-4091-bb9f-add557f3a9a2). Covers the ~249 BCI labels
# only. None disables match tier (d).
WCVP_CACHE_JSON = os.environ.get("BCI_WCVP_CACHE") or os.path.join(
    REPO, "data", "wcvp_cache.json")
if not os.path.exists(WCVP_CACHE_JSON):
    WCVP_CACHE_JSON = None

# global_key in the CSVs is "comb_<stem>.JPG"; cache file is "<stem>.JPG.json"
GT_KEY_PREFIX = "comb_"

CONF_BINS = [(0.0, 0.5), (0.5, 0.7), (0.7, 0.8), (0.8, 0.9), (0.9, 1.01)]
CONF_THRESHOLDS = [0.7, 0.8, 0.9]
SUPPORT_BUCKETS = [(1, 1, "1"), (2, 4, "2-4"), (5, 9, "5-9"),
                   (10, 24, "10-24"), (25, 10 ** 9, "25+")]
BUCKET_ORDER = [lab for _, _, lab in SUPPORT_BUCKETS]
WELL_SAMPLED_MIN_N = 10

# Send-first queue thresholds. Labelling buys most on the long tail and on weak
# guesses at usually-right species. Below LOW_CONF the calibration table puts
# the first guess right only ~38% of the time.
LOW_CONF = 0.5
WAIT_CONF = 0.8
# A species with at least this many labelled crowns and this measured top-1 is
# "usually right"; below HARD_MAX_TOP1 with enough crowns it is "hard".
RELIABLE_MIN_TOP1 = 0.90
HARD_MAX_TOP1 = 0.70
# A confident first guess that still disagrees with the botanist label is worth
# a second look: either the label or the model is wrong.
REVIEW_CONF = 0.8

# Predictions come from a fixed centre crop of the frame, while ground truth comes
# from crown boxes drawn anywhere in that frame, so a prediction can be scored
# against a label lying outside what the model was sent. A frame is admitted only
# when its dominant labelled species covers at least this fraction of the crop.
# Same value as crop_overlap.DEFAULT_MIN_COVERAGE.
MIN_CROP_COVERAGE = 0.50
# Reported as a sweep, so the gate's effect on the headline is visible rather than
# assumed from one threshold.
CROP_COVERAGE_SWEEP = (0.0, 0.3, 0.5, 0.8)


# --------------------------------------------------------------------------
# Name handling
# --------------------------------------------------------------------------
_BCI_CODE = re.compile(r"-[A-Z0-9]{5,7}$")
# Same idea before case folding, and down to 4 characters: the second code on a
# box label is short ('-ANAE', '-HURC', '-LUE1'). Upper case is what separates a
# code from a hyphenated epithet, so this can only run on the raw string.
_BCI_CODE_RAW = re.compile(r"-[A-Z0-9]{4,7}$")
_INFRA = re.compile(r"\b(var|subsp|ssp|f|cf|aff)\.?\s+\S+.*$", re.IGNORECASE)
_WS = re.compile(r"\s+")


def normalize(name: str) -> str:
    """Tier (b): case/whitespace/punctuation-normalized name.

    Strips accents, converts '_' separators to spaces, removes a trailing BCI
    collection code ('-QUARAS'), removes infraspecific ranks ('var. grandiflora'),
    collapses whitespace, lowercases. Does NOT resolve synonymy.
    """
    s = unicodedata.normalize("NFKD", name)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.replace("_", " ").strip()
    s = _BCI_CODE.sub("", s)
    s = _INFRA.sub("", s)
    return _WS.sub(" ", s).strip().lower()


def canonical_binomial(name):
    """Bare 'Genus species' from an authored accepted name.

    'Ocotea leptobotra (Ruiz & Pav.) Mez' -> 'Ocotea leptobotra'.
    Returns None when the first two tokens are not a plain binomial.
    (Same rule as speciesfirst.wcvp_export.canonical_binomial.)
    """
    if not name:
        return None
    tok = name.split()
    if len(tok) < 2:
        return None
    genus, epithet = tok[0], tok[1]
    core = epithet.replace("-", "").replace("×", "")
    if not genus[:1].isupper() or not core.isalpha() or not core.islower():
        return None
    return f"{genus} {epithet}"


def genus_of(n: str) -> str:
    return n.split(" ")[0] if n else ""


def is_species_level(n: str) -> bool:
    return len(n.split(" ")) >= 2


# --------------------------------------------------------------------------
# Loaders
# --------------------------------------------------------------------------
def read_csv_rows(path: str) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def salvage_species_array(text: str):
    """Extract results.species from a payload truncated inside
    per_tiles_embeddings. Bracket-matches the array after the "species" key."""
    i = text.find('"species"')
    if i < 0:
        return None
    i = text.find("[", i)
    if i < 0:
        return None
    depth = 0
    for j in range(i, len(text)):
        if text[j] == "[":
            depth += 1
        elif text[j] == "]":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[i:j + 1])
                except json.JSONDecodeError:
                    return None
    return None


def load_cache_entry(path: str):
    """-> (species_list, status). status in {ok, salvaged, unreadable}.
    per_tiles_embeddings is dropped immediately and never retained."""
    with open(path, encoding="utf-8", errors="replace") as f:
        text = f.read()
    try:
        return json.loads(text).get("results", {}).get("species", []) or [], "ok"
    except json.JSONDecodeError:
        pass
    try:  # valid JSON followed by trailing garbage
        obj, _ = json.JSONDecoder().raw_decode(text)
        return obj.get("results", {}).get("species", []) or [], "salvaged"
    except json.JSONDecodeError:
        pass
    sp = salvage_species_array(text)
    return (sp, "salvaged") if sp is not None else ([], "unreadable")


def load_wcvp_crosswalk(path):
    """-> (mapping normalized_input -> normalized_accepted_binomial, raw_entries).
    Only entries where the accepted binomial differs from the input are kept."""
    if not path or not os.path.exists(path):
        return {}, {}
    raw = json.load(open(path, encoding="utf-8"))
    mapping = {}
    for k, v in raw.items():
        acc = canonical_binomial(v.get("accepted_name"))
        if not acc:
            continue
        src, dst = normalize(k), normalize(acc)
        if src and dst and src != dst:
            mapping[src] = dst
    return mapping, raw


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------
def pct(num, den):
    return "n/a" if not den else f"{100.0 * num / den:.2f}%"


def ratio(num, den):
    return None if not den else num / den


def fmt(x, nd=4):
    return "" if x is None else f"{x:.{nd}f}"


def bucket_label(n: int) -> str:
    for lo, hi, lab in SUPPORT_BUCKETS:
        if lo <= n <= hi:
            return lab
    return "?"


# Queue names, in the order a botanist should work through them.
QUEUE_ORDER = ["long_tail", "low_conf_known", "normal", "can_wait"]

# Labelbox send batches: no more than this many crowns per batch, so a single
# send stays inside what one botanist session can review.
BATCH_SIZE = 100


def chunk_send_batches(queue_rows: list, batch_size: int = BATCH_SIZE) -> list:
    """Species-grouped, priority-first batches over an already-ordered queue.

    ``queue_rows`` is send_first_queue.csv's row order: queue priority first,
    then weakest confidence first inside a queue (see measure.py). This
    keeps that global priority order between species -- a species is only
    visited once, at the point its first (highest-priority) row occurs -- and
    groups every row for that species together so a Labelbox send is
    species-homogeneous, never spanning more than ``batch_size`` rows. Pure
    function of its input, so the same queue always chunks the same way.
    """
    order: list[str] = []
    seen: set[str] = set()
    by_species: dict[str, list] = defaultdict(list)
    for row in queue_rows:
        sp = row[3]  # predicted_species
        by_species[sp].append(row)
        if sp not in seen:
            seen.add(sp)
            order.append(sp)
    batches = []
    batch_id = 0
    for sp in order:
        rows = by_species[sp]
        for i in range(0, len(rows), batch_size):
            batch_id += 1
            for row in rows[i:i + batch_size]:
                batches.append([batch_id, sp, row[1], row[0]])
    return batches


def queue_of_prediction(pred: str, conf: float, support: dict, top1: dict) -> str:
    """Which queue an unlabelled crown lands in, from its first guess alone.

    ``support`` maps a GT species to its labelled-crown count, ``top1`` to its
    measured first-guess accuracy; a predicted species absent from both has
    never been labelled. First matching rule wins, so a weak guess on a rare
    species stays with the long tail rather than the anomaly queue.
    """
    n = support.get(pred, 0)
    a = top1.get(pred)
    if n < WELL_SAMPLED_MIN_N or (a is not None and a < HARD_MAX_TOP1):
        return "long_tail"
    if a is not None and a >= RELIABLE_MIN_TOP1 and conf < LOW_CONF:
        return "low_conf_known"
    if conf >= WAIT_CONF and n >= WELL_SAMPLED_MIN_N:
        return "can_wait"
    return "normal"


def diagnose(row: dict) -> str:
    """Per-species status. First matching rule wins; the order is the point.

    ``unreachable`` outranks everything because no amount of labelling moves it.
    ``reliable`` outranks ``ranking`` because a species already at >=90% does not
    need a re-rank. ``unmeasured`` sits below ``ranking`` so a thinly labelled
    species whose answer is in the list is still the cheap win it is.

    Lives here, not in a page module, so every dashboard renders the same
    status for the same species (same reason queue_of_prediction lives here).
    """
    n, a1, a5 = row["n_labelled_crowns"], row["top1_accuracy"], row["top5_accuracy"]
    if not row["in_corpus_vocabulary"]:
        return "unreachable"
    if n >= WELL_SAMPLED_MIN_N and a1 >= 0.90:
        return "reliable"
    if a5 - a1 >= 0.20 and a5 >= 0.60:
        return "ranking"
    if n < WELL_SAMPLED_MIN_N:
        return "unmeasured"
    return "hard" if a1 < 0.70 else "adequate"


# --------------------------------------------------------------------------
# Crop coverage gate
# --------------------------------------------------------------------------
def strip_collection_codes(name: str) -> str:
    """Drop every trailing BCI collection code, then normalize.

    The box CSV labels carry two ('Apeiba membranacea-APEIME-APEM'), and the
    second is often shorter than the code normalize() recognises ('-ANAE').
    Stripping has to happen before normalize() lowercases, because the codes are
    identified by being upper case and a lowered code can no longer be told from
    a hyphenated epithet. Without this a box label never compares equal to a GT
    species name.
    """
    s, prev = (name or "").strip(), None
    while s != prev:
        prev = s
        s = _BCI_CODE_RAW.sub("", s).strip()
    return normalize(s)


def coverage_split(recs, min_coverage=MIN_CROP_COVERAGE):
    """(admitted, rejected) over records carrying a ``crop_coverage`` field.

    A record whose frame has no measured box geometry carries None and is
    rejected: the gate admits only frames measured to be covered, never assumed
    ones. Rejected is therefore 'not admitted', which includes 'unknown'.
    """
    admitted, rejected = [], []
    for r in recs:
        c = r.get("crop_coverage")
        (admitted if c is not None and c >= min_coverage else rejected).append(r)
    return admitted, rejected


def coverage_gate_stats(recs, min_coverage=MIN_CROP_COVERAGE):
    """Headline numbers over the admitted subset of ``recs``.

    ``macro_top1`` averages per-species top-1 over the admitted rows only, and
    the species set shrinks with the threshold, so it is a different quantity
    from the ungated macro average: report it beside that number, never in place
    of it, and always with ``n_admitted``.
    """
    admitted, rejected = coverage_split(recs, min_coverage)
    by_sp = defaultdict(list)
    for r in admitted:
        by_sp[r["gt"]].append(r)
    hits = sum(1 for r in admitted if r["ranked"][0][0] == r["gt"])
    per = [sum(1 for r in rs if r["ranked"][0][0] == sp) / len(rs)
           for sp, rs in by_sp.items()]
    return {
        "min_coverage": min_coverage,
        "n_admitted": len(admitted),
        "n_rejected": len(rejected),
        "n_correct_top1": hits,
        "micro_top1": ratio(hits, len(admitted)),
        "macro_top1": (sum(per) / len(per)) if per else None,
        "n_species": len(by_sp),
    }


# --------------------------------------------------------------------------
@dataclass
class Health:
    gt_rows: list
    split_rows: list
    split_of: dict
    cache_files: list
    predictions: dict
    status_count: Counter
    length_hist: Counter
    corpus_vocab: Counter
    maxk: int
    n_entries: int
    n_cov_ne_score: int
    n_unsorted: int
    joined: list
    missing_cache: list
    crosswalk: dict
    wcvp_raw: dict
    corpus_norm: set
    corpus_genera: set
    corpus_raw: set
    corpus_canon: set
    gt_names: Counter
    tier_of_name: dict
    tier_names: Counter
    tier_crowns: Counter
    applied_synonyms: list
    absent_names: list
    genus_only_gt: list
    genus_in_corpus_only: list
    records: list
    sp_recs: list
    genus_recs: list
    per_species: list
    by_sp: dict
    canon: Callable[[str], str]
    crop_frames: dict
    crop_suspect: list
    crop_min_coverage: float
    n_crop_joined: int
    crop_admitted: list
    crop_rejected: list


def load_health(*, gt_csv=GT_CSV, splits_csv=SPLITS_CSV, cache_dir=CACHE_DIR,
                wcvp_cache=WCVP_CACHE_JSON, boxes_csv=None,
                min_coverage=MIN_CROP_COVERAGE,
                log: Optional[Callable[[str], None]] = None) -> Health:
    def _log(msg: str = "") -> None:
        if log is not None:
            log(msg)

    for p in (gt_csv, splits_csv, cache_dir):
        if not os.path.exists(p):
            raise FileNotFoundError(f"MISSING INPUT: {p}")
        _log(f"  input ok : {p}")
    _log(f"  wcvp cache: {wcvp_cache if wcvp_cache and os.path.exists(wcvp_cache) else 'ABSENT (tier d disabled)'}")
    _log("")

    # ---------------- 1. load GT + splits ----------------
    gt_rows = read_csv_rows(gt_csv)
    split_rows = read_csv_rows(splits_csv)
    split_of = {r["global_key"]: r["split"] for r in split_rows}

    _log("--- INPUTS ---")
    _log(f"gt_dominant_taxon.csv rows            : {len(gt_rows)}")
    _log(f"  distinct global_key                 : {len(set(r['global_key'] for r in gt_rows))}")
    _log(f"  distinct wcvp_canonical_name        : {len(set(r['wcvp_canonical_name'] for r in gt_rows))}")
    _log(f"splits.csv rows                       : {len(split_rows)}")
    sc = Counter(r["split"] for r in split_rows)
    for k in sorted(sc, key=lambda x: (-sc[x], x)):
        _log(f"  split '{k}'{'':<{max(0, 16 - len(k))}}: {sc[k]}")
    gt_split = Counter(split_of.get(r["global_key"], "<not in splits>") for r in gt_rows)
    _log("  split values among GT crowns        : " +
         ", ".join(f"{k or '<empty>'}={v}" for k, v in sorted(gt_split.items())))
    _log(f"  GT coverage of the photo corpus     : {len(gt_rows)} / {len(split_rows)} "
         f"= {pct(len(gt_rows), len(split_rows))} of photos carry a GT label.")
    _log("  That labelled subset is the historical botanist labelling record, not a")
    _log("  random draw, so per-species rates transfer to the unlabelled remainder only")
    _log("  under an assumption that cannot be tested offline.")
    _log("  NOTE: all evaluation below pools train+valid+test. The cached predictions")
    _log("  come from a frozen third-party API that never saw these splits, so there is")
    _log("  no train/test leakage to control for; splits are reported for traceability only.")
    _log("")

    # ---------------- 2. scan cache ----------------
    cache_files = sorted(f for f in os.listdir(cache_dir) if f.endswith(".json"))
    predictions, status_count, length_hist = {}, Counter(), Counter()
    corpus_vocab = Counter()
    n_entries = n_cov_ne_score = n_unsorted = 0

    for fn in cache_files:
        sp, status = load_cache_entry(os.path.join(cache_dir, fn))
        status_count[status] += 1
        ranked = []
        prev = None
        for e in sp:
            n_entries += 1
            if e.get("coverage") != e.get("max_score"):
                n_cov_ne_score += 1
            s = float(e.get("max_score") or 0.0)
            if prev is not None and s > prev + 1e-12:
                n_unsorted += 1
            prev = s
            b = (e.get("binomial") or "").strip()
            if b:
                ranked.append((b, s))
        predictions[fn[:-5]] = ranked
        length_hist[len(ranked)] += 1
        for b, _ in ranked:
            corpus_vocab[normalize(b)] += 1

    _log("--- CACHED PREDICTIONS: PROVENANCE ---")
    _log("  Read from predict/ingest_photos.py + config.yaml")
    _log("  + bin/sbatch_ingest.sh (the run that filled this cache):")
    _log("    endpoint : https://my-api.plantnet.org/v2/identify/k-central-america")
    _log("               -> the CENTRAL AMERICA regional model, NOT the global Pl@ntNet model.")
    _log("               The sbatch job passes no --survey-endpoint, so the 2-call")
    _log("               identify+embeddings fallback ran, not /v2/survey/.")
    _log("    model    : config.yaml single_model_run_name 'v7.4-2026-03-27'")
    _log("    params   : nb-results=5, no-reject=true, organs=auto, include-related-images=false")
    _log("    input    : 1280 px CENTRE CROP of each crown photo (CROP_SIZE=1280), not the full frame")
    _log("    'coverage'/'max_score' in the cached JSON are BOTH the identify confidence")
    _log("    score, copied twice by identify_to_survey_json(); there is no real coverage")
    _log("    signal here. Pl@ntNet identify scores are normalised across returned results.")
    _log("    No client-side score threshold is applied, so a list shorter than 5 came back")
    _log("    short from the API itself.")
    _log("")
    _log("--- CACHED PREDICTIONS: PARSE ---")
    _log(f"cache .json files                     : {len(cache_files)}")
    for k in ("ok", "salvaged", "unreadable"):
        _log(f"  parsed {k:<30}: {status_count.get(k, 0)}")
    _log("  ('salvaged' = payload truncated inside per_tiles_embeddings; the ranked")
    _log("   species array precedes it and was recovered by bracket-matching.)")
    _log("  prediction-list length histogram    : " +
         ", ".join(f"len={k}:{v}" for k, v in sorted(length_hist.items())))
    maxk = max(length_hist)
    _log(f"  MAX list length observed            : {maxk}")
    _log(f"  => 'top-5' IS the full returned list. The cap is the client-side request")
    _log("     parameter nb-results=5 (config.yaml plantnet.identify_nb_results), not a")
    _log("     model limit: a re-ingest with a larger nb-results would return more. No")
    _log("     deeper candidate exists in this cache and none can be recovered offline.")
    _log(f"  total candidate entries             : {n_entries}")
    _log(f"  entries where coverage != max_score : {n_cov_ne_score}  "
         f"(0 confirms both fields hold the same identify score)")
    _log(f"  entries breaking descending order   : {n_unsorted}  "
         f"(0 confirms the list is ranked; index 0 is top-1)")
    _log(f"  distinct predicted binomials        : {len(corpus_vocab)}")
    _log("")

    # ---------------- 3. join ----------------
    joined, missing_cache = [], []
    for r in gt_rows:
        gk = r["global_key"]
        stem = gk[len(GT_KEY_PREFIX):] if gk.startswith(GT_KEY_PREFIX) else gk
        if stem in predictions:
            joined.append((gk, stem, r["wcvp_canonical_name"]))
        else:
            missing_cache.append(gk)

    _log("--- JOIN (global_key -> cache file) ---")
    _log(f"  convention                          : GT '{GT_KEY_PREFIX}<stem>.JPG'  ->  cache '<stem>.JPG.json'")
    _log(f"  byte-exact key join                 : 0 / {len(gt_rows)}   (GT keys carry the '{GT_KEY_PREFIX}' prefix; cache names do not)")
    _log(f"  after stripping '{GT_KEY_PREFIX}'            : {len(joined)} / {len(gt_rows)}   ({pct(len(joined), len(gt_rows))})")
    _log(f"  GT crowns with no cached response   : {len(missing_cache)}")
    for gk in sorted(missing_cache):
        _log(f"      {gk}")
    _log(f"  joined but empty prediction list    : {sum(1 for _, s, _ in joined if not predictions[s])}")
    _log("")

    # ---------------- 4. name reconciliation tiers ----------------
    crosswalk, wcvp_raw = load_wcvp_crosswalk(wcvp_cache)
    corpus_norm = set(corpus_vocab)
    corpus_genera = {genus_of(b) for b in corpus_norm if b}
    # raw (un-normalized) predicted binomials, for the byte-exact tier (a)
    corpus_raw = {b for ranked in predictions.values() for b, _ in ranked}

    gt_names = Counter(r["wcvp_canonical_name"] for r in gt_rows)
    tier_of_name, tier_names, tier_crowns = {}, Counter(), Counter()
    applied_synonyms, absent_names, genus_only_gt, genus_in_corpus_only = [], [], [], []

    for name, cnt in gt_names.items():
        nn = normalize(name)
        mapped = crosswalk.get(nn)
        if not is_species_level(nn):
            t = "c_gt_label_is_genus_only"
            genus_only_gt.append((name, cnt))
        elif name in corpus_raw:
            t = "a_exact_binomial"
        elif nn in corpus_norm:
            t = "b_normalized"
        elif mapped and mapped in corpus_norm:
            t = "d_wcvp_synonym"
            applied_synonyms.append((name, mapped, cnt))
        elif genus_of(mapped or nn) in corpus_genera:
            t = "c_genus_only_in_corpus"
            genus_in_corpus_only.append((name, mapped, cnt))
        else:
            t = "e_absent_from_corpus"
            absent_names.append((name, mapped, cnt))
        tier_of_name[name] = t
        tier_names[t] += 1
        tier_crowns[t] += cnt

    _log("--- NAME RECONCILIATION ---")
    _log("  GT column is called 'wcvp_canonical_name' but IS NOT WCVP-resolved: it is a")
    _log("  string-strip of the Labelbox field label (see labelling/")
    _log("  gt_from_export.py). Hence trailing collection codes ('-QUARAS')")
    _log("  and pre-revision synonyms ('Arrabidaea candicans') survive in it.")
    _log("")
    _log("  'corpus vocabulary' = every distinct binomial appearing anywhere in the")
    _log(f"  {len(cache_files)} cached top-{maxk} lists ({len(corpus_vocab)} names). It is NOT Pl@ntNet's full")
    _log("  label set: a species the model knows but never ranked top-5 on any BCI photo")
    _log("  is indistinguishable here from a species the model does not know at all.")
    _log("")
    _log(f"  {'tier':<28} {'distinct GT names':>18} {'GT crowns':>10}")
    for t in ("a_exact_binomial", "b_normalized", "d_wcvp_synonym",
              "c_gt_label_is_genus_only", "c_genus_only_in_corpus", "e_absent_from_corpus"):
        _log(f"  {t:<28} {tier_names.get(t, 0):>18} {tier_crowns.get(t, 0):>10}")
    _log(f"  crosswalk entries loaded            : {len(crosswalk)} name changes from "
         f"{len(wcvp_raw)} WCVP cache records")
    _log("")
    _log("  (d) WCVP synonym mappings actually APPLIED (audit these):")
    for name, mapped, cnt in sorted(applied_synonyms, key=lambda x: -x[2]):
        _log(f"      {cnt:>4} crowns  {name}  ->  {mapped}")
    _log("")
    _log("  CEILING ON ACHIEVABLE SPECIES-LEVEL ACCURACY")
    ceil_names = tier_names["e_absent_from_corpus"] + tier_names["c_genus_only_in_corpus"]
    ceil_crowns = tier_crowns["e_absent_from_corpus"] + tier_crowns["c_genus_only_in_corpus"]
    _log(f"      {ceil_crowns} GT crowns across {ceil_names} species can NEVER be scored correct from")
    _log("      this cache: after normalization and WCVP synonym resolution their name")
    _log(f"      still appears in no cached prediction list. ({ceil_crowns} is out of all {len(gt_rows)} GT")
    _log("      rows; the subset falling inside the primary evaluation set is reported")
    _log("      under HEADLINE as the 'restricted to reachable crowns' line.)")
    _log("")
    _log("  GT species whose genus IS in the corpus but the exact epithet is not:")
    for name, mapped, cnt in sorted(genus_in_corpus_only, key=lambda x: -x[2]):
        _log(f"      {cnt:>4} crowns  {name}" + (f"  (wcvp-> {mapped})" if mapped else ""))
    _log("")
    _log("  GT species absent from the corpus entirely (genus not seen either):")
    for name, mapped, cnt in sorted(absent_names, key=lambda x: -x[2]):
        _log(f"      {cnt:>4} crowns  {name}" + (f"  (wcvp-> {mapped})" if mapped else ""))
    _log("")
    _log(f"  GT labels the botanist left at genus level: {tier_names['c_gt_label_is_genus_only']} genera, "
         f"{tier_crowns['c_gt_label_is_genus_only']} crowns.")
    _log("      EXCLUDED from the species-level headline; scored separately at genus level.")
    _log("")

    # ---------------- 5. build evaluable records ----------------
    def canon(name: str) -> str:
        """Normalize + apply the local WCVP crosswalk (tiers a-d)."""
        nn = normalize(name)
        return crosswalk.get(nn, nn)

    # Coverage of the crop the model was sent, joined on base_image. GT keys carry
    # the GT_KEY_PREFIX and the box CSV does not, so the same stem used for the
    # cache join is the join key here too.
    #
    # Imported here, not at module level: crop_overlap imports ``normalize``
    # from this module, so a module-level import here would close the cycle.
    import crop_overlap
    crop_frames, crop_suspect = crop_overlap.build(
        **({"path": boxes_csv} if boxes_csv else {}))

    records = []
    for gk, stem, gt_name in joined:
        gt_c = canon(gt_name)
        cov = crop_frames.get(stem)
        records.append({
            "global_key": gk,
            "split": split_of.get(gk, ""),
            "gt_raw": gt_name,
            "gt": gt_c,
            "gt_strict": normalize(gt_name),
            "species_level": is_species_level(gt_c),
            "ranked": [(canon(b), s) for b, s in predictions[stem]],
            "ranked_strict": [(normalize(b), s) for b, s in predictions[stem]],
            # None means the frame has no box row at all, so its coverage is
            # unknown rather than zero. The dominant name is put through the same
            # canonicalisation as the GT label so the two are comparable.
            "crop_coverage": cov["coverage"] if cov else None,
            "crop_dominant": (canon(cov["dominant"])
                              if cov and cov["dominant"] else None),
        })

    sp_recs = [r for r in records if r["species_level"] and r["ranked"]]
    genus_recs = [r for r in records if not r["species_level"] and r["ranked"]]

    n_crop_joined = sum(1 for r in records if r["crop_coverage"] is not None)
    crop_admitted, crop_rejected = coverage_split(sp_recs, min_coverage)
    _log("--- CROP COVERAGE GATE ---")
    _log("  Predictions were made from a fixed centre crop of each frame; ground truth")
    _log("  boxes are drawn anywhere in the frame. A frame is admitted only when its")
    _log("  dominant labelled species covers at least the threshold share of that crop.")
    _log(f"  box geometry available for          : {len(crop_frames)} base frames "
         f"({len(crop_suspect)} frames not trusted and excluded)")
    _log(f"  joined to a GT record               : {n_crop_joined} / {len(records)} "
         f"({pct(n_crop_joined, len(records))})")
    n_sp_cov = sum(1 for r in sp_recs if r["crop_coverage"] is not None)
    _log(f"  joined within the primary set       : {n_sp_cov} / {len(sp_recs)} "
         f"({pct(n_sp_cov, len(sp_recs))})")
    _log(f"  admitted at coverage >= {min_coverage:.2f}        : {len(crop_admitted)} "
         f"(rejected {len(crop_rejected)}, of which "
         f"{len(sp_recs) - n_sp_cov} for unknown geometry)")
    _log("")

    # ---------------- 7. per-species ----------------
    def top1(r, key="ranked"):
        return r[key][0][0]

    def hit(r, k, key="ranked", gtkey="gt"):
        return r[gtkey] in [b for b, _ in r[key][:k]]

    by_sp = defaultdict(list)
    for r in sp_recs:
        by_sp[r["gt"]].append(r)

    corpus_canon = {canon(b) for b in corpus_raw}
    per_species = []
    for sp, rs in by_sp.items():
        m = len(rs)
        k1 = sum(1 for r in rs if top1(r) == sp)
        k5 = sum(1 for r in rs if hit(r, 5))
        confs_ok = [r["ranked"][0][1] for r in rs if top1(r) == sp]
        per_species.append({
            "species": sp,
            "gt_raw_labels": "|".join(sorted({r["gt_raw"] for r in rs})),
            "n_labelled_crowns": m,
            "n_correct_top1": k1,
            "top1_accuracy": k1 / m,
            "n_correct_top5": k5,
            "top5_accuracy": k5 / m,
            "mean_top1_confidence": sum(r["ranked"][0][1] for r in rs) / m,
            "mean_top1_confidence_when_correct": (sum(confs_ok) / len(confs_ok)) if confs_ok else None,
            "in_corpus_vocabulary": sp in corpus_norm or sp in corpus_canon,
            "support_bucket": bucket_label(m),
        })
    per_species.sort(key=lambda d: (-d["n_labelled_crowns"], d["species"]))

    return Health(
        gt_rows=gt_rows, split_rows=split_rows, split_of=split_of,
        cache_files=cache_files, predictions=predictions, status_count=status_count,
        length_hist=length_hist, corpus_vocab=corpus_vocab, maxk=maxk,
        n_entries=n_entries, n_cov_ne_score=n_cov_ne_score, n_unsorted=n_unsorted,
        joined=joined, missing_cache=missing_cache, crosswalk=crosswalk,
        wcvp_raw=wcvp_raw, corpus_norm=corpus_norm, corpus_genera=corpus_genera,
        corpus_raw=corpus_raw, corpus_canon=corpus_canon, gt_names=gt_names,
        tier_of_name=tier_of_name, tier_names=tier_names, tier_crowns=tier_crowns,
        applied_synonyms=applied_synonyms, absent_names=absent_names,
        genus_only_gt=genus_only_gt, genus_in_corpus_only=genus_in_corpus_only,
        records=records, sp_recs=sp_recs, genus_recs=genus_recs,
        per_species=per_species, by_sp=by_sp, canon=canon,
        crop_frames=crop_frames, crop_suspect=crop_suspect,
        crop_min_coverage=min_coverage, n_crop_joined=n_crop_joined,
        crop_admitted=crop_admitted, crop_rejected=crop_rejected,
    )
