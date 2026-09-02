"""Pl@ntNet-on-BCI model health: the data layer every page reads.

Deterministic, no network. Loads labels, splits and predictions; joins
and reconciles names (optionally via a WCVP crosswalk); builds per-frame
records and per-species aggregates.
"""

from __future__ import annotations

import csv
import datetime as _dt
import json
import os
import re
import unicodedata
from collections import Counter, defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from types import SimpleNamespace

# --- INPUT PATHS ---
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

# global_key -> (data_row_id, project_id), accumulated by
# labelling/gt_from_export.py from the exports the GT was merged from. The one
# offline source for a Labelbox deep link: a data row opens only inside a
# project it belongs to, and the export states both halves. Absent, or missing
# a frame labelled in a project that has not been exported since, the page
# reports the gap rather than guessing a URL.
DATA_ROW_IDS_CSV = os.path.join(BASE, "data_row_ids.csv")
LABELBOX_URL = "https://app.labelbox.com/projects/{project_id}/data-rows/{data_row_id}"

# Botanist verdicts on frames the review queue raised. A confident disagreement
# is either a label error or a model error, and offline nothing can tell which;
# once a botanist has ruled, the frame must stop reappearing, because the
# prediction never changes and the queue would otherwise raise it forever.
# Tracked in git: an untracked verdict is lost on the next clone.
ADJUDICATIONS_CSV = os.path.join(BASE, "adjudications.csv")
# The one verdict that suppresses a frame. A label ruled wrong is fixed in
# Labelbox instead, where the next export carries the correction, so it needs
# no entry here.
LABEL_CONFIRMED = "label_confirmed_prediction_wrong"

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


def gt_provenance(gt_csv: str = GT_CSV) -> str:
    """One line naming the export the ground truth was merged from.

    Reads the sidecar ``labelling/gt_from_export.py`` writes at merge,
    falling back to the file's mtime. Lives here so every page agrees.
    """
    sidecar = os.path.splitext(gt_csv)[0] + ".provenance.txt"
    if os.path.exists(sidecar):
        with open(sidecar, encoding="utf-8") as f:
            return f.read().strip()
    mtime = _dt.date.fromtimestamp(os.path.getmtime(gt_csv)).isoformat()
    return f"Ground truth: {os.path.basename(gt_csv)}, dated {mtime}."

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

# Predictions come from a fixed centre crop; labels come from boxes drawn anywhere
# in the frame, so a label can lie outside what the model was sent. A frame is
# admitted only when its dominant species fills this much of the crop.
MIN_CROP_COVERAGE = 0.50
# Reported as a sweep, so the gate's effect on the headline is visible rather than
# assumed from one threshold.
CROP_COVERAGE_SWEEP = (0.0, 0.3, 0.5, 0.8)


# --- Name handling ---
_BCI_CODE = re.compile(r"-[A-Z0-9]{5,7}$")
# Same idea before case folding, and down to 4 characters: the second code on a
# box label is short ('-ANAE', '-HURC', '-LUE1'). Upper case is what separates a
# code from a hyphenated epithet, so this can only run on the raw string.
_BCI_CODE_RAW = re.compile(r"-[A-Z0-9]{4,7}$")
_INFRA = re.compile(r"\b(var|subsp|ssp|f|cf|aff)\.?\s+\S+.*$", re.IGNORECASE)
_WS = re.compile(r"\s+")


def normalize(name: str) -> str:
    """Tier (b): normalized name. Strips accents, converts '_' to spaces,
    drops a trailing BCI collection code and infraspecific ranks
    ('var. grandiflora'), collapses whitespace, lowercases. Does not resolve
    synonymy.
    """
    s = unicodedata.normalize("NFKD", name)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.replace("_", " ").strip()
    s = _BCI_CODE.sub("", s)
    s = _INFRA.sub("", s)
    return _WS.sub(" ", s).strip().lower()


def canonical_binomial(name):
    """Bare 'Genus species' from an authored accepted name.

    'Ocotea leptobotra (Ruiz & Pav.) Mez' -> 'Ocotea leptobotra'. None if
    the first two tokens are not a plain binomial. (Same rule as
    speciesfirst.wcvp_export.canonical_binomial.)
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


# --- Loaders ---
def read_csv_rows(path: str) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def labelbox_urls(path: str = DATA_ROW_IDS_CSV) -> dict[str, str]:
    """global_key -> Labelbox URL, where known.

    Reads a file, never the API: no network call, no credential. Missing
    file is an empty map; caller reports coverage.
    """
    if not os.path.exists(path):
        return {}
    out = {}
    for r in read_csv_rows(path):
        if r.get("data_row_id") and r.get("project_id"):
            out[r["global_key"]] = LABELBOX_URL.format(
                project_id=r["project_id"], data_row_id=r["data_row_id"])
    return out


def adjudicated_keys(path: str = ADJUDICATIONS_CSV) -> set[str]:
    """global_keys a botanist ruled label-confirmed; the review queue drops them.

    Missing file is an empty set. Other verdicts are ignored, not
    rejected, so the file can record rulings this queue skips.
    """
    if not os.path.exists(path):
        return set()
    return {r["global_key"] for r in read_csv_rows(path)
            if r.get("global_key") and r.get("verdict") == LABEL_CONFIRMED}


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
    with open(path, encoding="utf-8") as fh:
        raw = json.load(fh)
    mapping = {}
    for k, v in raw.items():
        acc = canonical_binomial(v.get("accepted_name"))
        if not acc:
            continue
        src, dst = normalize(k), normalize(acc)
        if src and dst and src != dst:
            mapping[src] = dst
    return mapping, raw


# --- Small helpers ---
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
    """Species-grouped, priority-first batches over an already-ordered
    ``queue_rows`` (send_first_queue.csv order). Each species is visited
    once, at its highest-priority row; its rows travel together, packed
    whole until the next would overflow ``batch_size``, then split.
    """
    if batch_size < 1:
        raise ValueError(f"batch_size must be at least 1, got {batch_size}")
    order: list[str] = []
    seen: set[str] = set()
    by_species: dict[str, list] = defaultdict(list)
    for row in queue_rows:
        sp = row[3]  # predicted_species
        by_species[sp].append(row)
        if sp not in seen:
            seen.add(sp)
            order.append(sp)

    # One group per species, split first so an oversized species cannot
    # straddle a batch boundary; the trailing part packs like any other group.
    groups = [(sp, by_species[sp][i:i + batch_size])
              for sp in order
              for i in range(0, len(by_species[sp]), batch_size)]

    batches = []
    batch_id = 0
    held = batch_size  # rows already in the open batch; forces the first one open
    for sp, rows in groups:
        if held + len(rows) > batch_size:
            batch_id += 1
            held = 0
        held += len(rows)
        for row in rows:
            batches.append([batch_id, sp, row[1], row[0]])
    return batches


def queue_of_prediction(pred: str, conf: float, support: dict, top1: dict) -> str:
    """Which queue an unlabelled crown lands in, from its first guess alone.

    ``support``: labelled-crown count per species. ``top1``: measured
    accuracy per species. Absent from both means never labelled. First
    rule wins, so a weak guess on a rare species stays in the long tail.
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
    """Per-species status. First matching rule wins; order is the point.

    ``unreachable`` outranks all; no labelling helps. ``reliable`` outranks
    ``ranking``: >=90% needs no re-rank. ``unmeasured`` sits below
    ``ranking``, so a thin species already in the list counts as cheap.
    """
    n, a1, a5 = row["n_labelled_crowns"], row["top1_accuracy"], row["top5_accuracy"]
    if not row["in_corpus_vocabulary"]:
        return "unreachable"
    if n >= WELL_SAMPLED_MIN_N and a1 >= RELIABLE_MIN_TOP1:
        return "reliable"
    if a5 - a1 >= 0.20 and a5 >= 0.60:
        return "ranking"
    if n < WELL_SAMPLED_MIN_N:
        return "unmeasured"
    return "hard" if a1 < HARD_MAX_TOP1 else "adequate"


# The order above, as data, because the pages have to say it. A reader who takes
# "fewer than 10 labelled frames" as a threshold and sorts on the status column
# meets one-frame species tagged as cheap confirmation work, and nothing on the
# page explains why. The last two statuses are decided by accuracy alone, so the
# tuple stops where the ordering stops mattering. A test walks ``diagnose`` to
# check this stays true.
STATUS_PRECEDENCE = ("unreachable", "reliable", "ranking", "unmeasured")


# --- Crop coverage gate ---
def strip_collection_codes(name: str) -> str:
    """Drop every trailing BCI collection code, then normalize.

    Box labels carry two codes; the second can be shorter than what
    normalize() recognizes ('-ANAE'). Strip first: codes are upper case,
    so a lowered one cannot be told from a hyphenated epithet.
    """
    s, prev = (name or "").strip(), None
    while s != prev:
        prev = s
        s = _BCI_CODE_RAW.sub("", s).strip()
    return normalize(s)


def coverage_split(recs, min_coverage=MIN_CROP_COVERAGE):
    """(admitted, rejected) over records carrying a ``crop_coverage`` field.

    A frame with no measured geometry carries None and is rejected: the
    gate admits only measured coverage, never assumed.
    """
    admitted, rejected = [], []
    for r in recs:
        c = r.get("crop_coverage")
        (admitted if c is not None and c >= min_coverage else rejected).append(r)
    return admitted, rejected


def coverage_gate_stats(recs, min_coverage=MIN_CROP_COVERAGE):
    """Headline numbers over the admitted subset of ``recs``.

    ``macro_top1`` averages per-species top-1 over admitted rows only, so
    its species set shrinks with threshold; report it beside the ungated
    macro average, with ``n_admitted``.
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
    predictions: dict
    maxk: int
    joined: list
    missing_cache: list
    crosswalk: dict
    corpus_norm: set
    corpus_canon: set
    gt_names: Counter
    tier_of_name: dict
    tier_crowns: Counter
    records: list
    sp_recs: list
    genus_recs: list
    per_species: list
    canon: Callable[[str], str]


def scan_cache(cache_dir):
    """Every cached Pl@ntNet response, read once.

    Returns the ranked list per photo stem, plus counts for the run log:
    parse status, list-length histogram, and two invariants pages assume,
    score fields match and lists descend.
    """
    files = sorted(f for f in os.listdir(cache_dir) if f.endswith(".json"))
    predictions, status_count, length_hist = {}, Counter(), Counter()
    corpus_vocab = Counter()
    n_entries = n_cov_ne_score = n_unsorted = 0

    for fn in files:
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

    return SimpleNamespace(
        files=files, predictions=predictions, status_count=status_count,
        length_hist=length_hist, corpus_vocab=corpus_vocab, n_entries=n_entries,
        n_cov_ne_score=n_cov_ne_score, n_unsorted=n_unsorted, maxk=max(length_hist))


def _log_cache(_log, s):
    """Run-log block on the cache. Text only; every number is in ``s``."""
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
    _log(f"cache .json files                     : {len(s.files)}")
    for k in ("ok", "salvaged", "unreadable"):
        _log(f"  parsed {k:<30}: {s.status_count.get(k, 0)}")
    _log("  ('salvaged' = payload truncated inside per_tiles_embeddings; the ranked")
    _log("   species array precedes it and was recovered by bracket-matching.)")
    _log("  prediction-list length histogram    : " +
         ", ".join(f"len={k}:{v}" for k, v in sorted(s.length_hist.items())))
    _log(f"  MAX list length observed            : {s.maxk}")
    _log("  => 'top-5' IS the full returned list. The cap is the client-side request")
    _log("     parameter nb-results=5 (config.yaml plantnet.identify_nb_results), not a")
    _log("     model limit: a re-ingest with a larger nb-results would return more. No")
    _log("     deeper candidate exists in this cache and none can be recovered offline.")
    _log(f"  total candidate entries             : {s.n_entries}")
    _log(f"  entries where coverage != max_score : {s.n_cov_ne_score}  "
         f"(0 confirms both fields hold the same identify score)")
    _log(f"  entries breaking descending order   : {s.n_unsorted}  "
         f"(0 confirms the list is ranked; index 0 is top-1)")
    _log(f"  distinct predicted binomials        : {len(s.corpus_vocab)}")
    _log("")


def reconcile_names(gt_rows, predictions, corpus_vocab, crosswalk):
    """Sort every botanist label into a tier against names the cache
    returned: byte-exact, normalized match, WCVP synonym, genus-only, or
    absent from every list. The last two are the ceiling pages report.
    """
    corpus_norm = set(corpus_vocab)
    corpus_genera = {genus_of(b) for b in corpus_norm if b}
    # raw (un-normalized) predicted binomials, for the byte-exact tier (a)
    corpus_raw = {b for ranked in predictions.values() for b, _ in ranked}

    gt_names = Counter(r["wcvp_canonical_name"] for r in gt_rows)
    tier_of_name, tier_names, tier_crowns = {}, Counter(), Counter()
    applied_synonyms, absent_names, genus_in_corpus_only = [], [], []

    for name, cnt in gt_names.items():
        nn = normalize(name)
        mapped = crosswalk.get(nn)
        if not is_species_level(nn):
            t = "c_gt_label_is_genus_only"
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

    return SimpleNamespace(
        corpus_norm=corpus_norm, corpus_raw=corpus_raw, gt_names=gt_names,
        tier_of_name=tier_of_name, tier_names=tier_names, tier_crowns=tier_crowns,
        applied_synonyms=applied_synonyms, absent_names=absent_names,
        genus_in_corpus_only=genus_in_corpus_only)


def _log_reconciliation(_log, n, scan, gt_rows, crosswalk, wcvp_raw):
    """Run-log block on name matching, including the ceiling line pages
    quote. Text only; every number is in ``n``."""
    _log("--- NAME RECONCILIATION ---")
    _log("  GT column is called 'wcvp_canonical_name' but IS NOT WCVP-resolved: it is a")
    _log("  string-strip of the Labelbox field label (see labelling/")
    _log("  gt_from_export.py). Hence trailing collection codes ('-QUARAS')")
    _log("  and pre-revision synonyms ('Arrabidaea candicans') survive in it.")
    _log("")
    _log("  'corpus vocabulary' = every distinct binomial appearing anywhere in the")
    _log(f"  {len(scan.files)} cached top-{scan.maxk} lists ({len(scan.corpus_vocab)} names). It is NOT Pl@ntNet's full")
    _log("  label set: a species the model knows but never ranked top-5 on any BCI photo")
    _log("  is indistinguishable here from a species the model does not know at all.")
    _log("")
    _log(f"  {'tier':<28} {'distinct GT names':>18} {'GT crowns':>10}")
    for t in ("a_exact_binomial", "b_normalized", "d_wcvp_synonym",
              "c_gt_label_is_genus_only", "c_genus_only_in_corpus", "e_absent_from_corpus"):
        _log(f"  {t:<28} {n.tier_names.get(t, 0):>18} {n.tier_crowns.get(t, 0):>10}")
    _log(f"  crosswalk entries loaded            : {len(crosswalk)} name changes from "
         f"{len(wcvp_raw)} WCVP cache records")
    _log("")
    _log("  (d) WCVP synonym mappings actually APPLIED (audit these):")
    for name, mapped, cnt in sorted(n.applied_synonyms, key=lambda x: -x[2]):
        _log(f"      {cnt:>4} crowns  {name}  ->  {mapped}")
    _log("")
    _log("  CEILING ON ACHIEVABLE SPECIES-LEVEL ACCURACY")
    ceil_names = n.tier_names["e_absent_from_corpus"] + n.tier_names["c_genus_only_in_corpus"]
    ceil_crowns = n.tier_crowns["e_absent_from_corpus"] + n.tier_crowns["c_genus_only_in_corpus"]
    _log(f"      {ceil_crowns} GT crowns across {ceil_names} species can NEVER be scored correct from")
    _log("      this cache: after normalization and WCVP synonym resolution their name")
    _log(f"      still appears in no cached prediction list. ({ceil_crowns} is out of all {len(gt_rows)} GT")
    _log("      rows; the subset falling inside the primary evaluation set is reported")
    _log("      under HEADLINE as the 'restricted to reachable crowns' line.)")
    _log("")
    _log("  GT species whose genus IS in the corpus but the exact epithet is not:")
    for name, mapped, cnt in sorted(n.genus_in_corpus_only, key=lambda x: -x[2]):
        _log(f"      {cnt:>4} crowns  {name}" + (f"  (wcvp-> {mapped})" if mapped else ""))
    _log("")
    _log("  GT species absent from the corpus entirely (genus not seen either):")
    for name, mapped, cnt in sorted(n.absent_names, key=lambda x: -x[2]):
        _log(f"      {cnt:>4} crowns  {name}" + (f"  (wcvp-> {mapped})" if mapped else ""))
    _log("")
    _log(f"  GT labels the botanist left at genus level: {n.tier_names['c_gt_label_is_genus_only']} genera, "
         f"{n.tier_crowns['c_gt_label_is_genus_only']} crowns.")
    _log("      EXCLUDED from the species-level headline; scored separately at genus level.")
    _log("")


def _log_inputs(_log, gt_rows, split_rows, split_of):
    """Run-log block on the two input CSVs, including the line pages
    repeat: the labelled subset is a record, not a random draw."""
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


def _log_join(_log, gt_rows, joined, missing_cache, predictions):
    """Run-log block on matching a label row to its cached answer,
    including every label with none."""
    _log("--- JOIN (global_key -> cache file) ---")
    _log(f"  convention                          : GT '{GT_KEY_PREFIX}<stem>.JPG'  ->  cache '<stem>.JPG.json'")
    _log(f"  byte-exact key join                 : 0 / {len(gt_rows)}   (GT keys carry the '{GT_KEY_PREFIX}' prefix; cache names do not)")
    _log(f"  after stripping '{GT_KEY_PREFIX}'            : {len(joined)} / {len(gt_rows)}   ({pct(len(joined), len(gt_rows))})")
    _log(f"  GT crowns with no cached response   : {len(missing_cache)}")
    for gk in sorted(missing_cache):
        _log(f"      {gk}")
    _log(f"  joined but empty prediction list    : {sum(1 for _, s, _ in joined if not predictions[s])}")
    _log("")


def _log_crop_gate(_log, records, sp_recs, crop_frames, crop_suspect,
                   n_crop_joined, crop_admitted, crop_rejected, min_coverage):
    """Run-log block on the crop-coverage gate. Pages report it as a
    diagnostic sweep, never a filter behind a headline."""
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


def aggregate_per_species(sp_recs, corpus_norm, corpus_canon):
    """One row per species: labelled frame count, first-guess and top-5
    accuracy, mean confidence.

    ``figures.N_CANDIDATES`` states the five-name list for the pages and
    aborts a build whose cache carries more.
    """
    def top1(r):
        return r["ranked"][0][0]

    by_sp = defaultdict(list)
    for r in sp_recs:
        by_sp[r["gt"]].append(r)

    per_species = []
    for sp, rs in by_sp.items():
        m = len(rs)
        k1 = sum(1 for r in rs if top1(r) == sp)
        k5 = sum(1 for r in rs if sp in [b for b, _ in r["ranked"][:5]])
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
    return per_species


def load_health(*, gt_csv=GT_CSV, splits_csv=SPLITS_CSV, cache_dir=CACHE_DIR,
                wcvp_cache=WCVP_CACHE_JSON,
                log: Callable[[str], None] | None = None) -> Health:
    def _log(msg: str = "") -> None:
        if log is not None:
            log(msg)

    for p in (gt_csv, splits_csv, cache_dir):
        if not os.path.exists(p):
            raise FileNotFoundError(f"MISSING INPUT: {p}")
        _log(f"  input ok : {p}")
    _log(f"  wcvp cache: {wcvp_cache if wcvp_cache and os.path.exists(wcvp_cache) else 'ABSENT (tier d disabled)'}")
    _log("")

    # ---------------- 1. the two input CSVs ----------------
    gt_rows = read_csv_rows(gt_csv)
    split_rows = read_csv_rows(splits_csv)
    split_of = {r["global_key"]: r["split"] for r in split_rows}

    _log_inputs(_log, gt_rows, split_rows, split_of)

    # ---------------- 2. every cached Pl@ntNet answer ----------------
    scan = scan_cache(cache_dir)
    predictions, maxk = scan.predictions, scan.maxk
    corpus_vocab = scan.corpus_vocab
    _log_cache(_log, scan)

    # ---------------- 3. match each label row to its cached answer ----------
    joined, missing_cache = [], []
    for r in gt_rows:
        gk = r["global_key"]
        stem = gk.removeprefix(GT_KEY_PREFIX)
        if stem in predictions:
            joined.append((gk, stem, r["wcvp_canonical_name"]))
        else:
            missing_cache.append(gk)

    _log_join(_log, gt_rows, joined, missing_cache, predictions)

    # ---------------- 4. sort each label into a name-matching tier ----------
    crosswalk, wcvp_raw = load_wcvp_crosswalk(wcvp_cache)
    names = reconcile_names(gt_rows, predictions, corpus_vocab, crosswalk)
    corpus_norm, corpus_raw = names.corpus_norm, names.corpus_raw
    gt_names, tier_of_name = names.gt_names, names.tier_of_name
    tier_crowns = names.tier_crowns
    _log_reconciliation(_log, names, scan, gt_rows, crosswalk, wcvp_raw)

    # ---------------- 5. one record per frame we can score ----------------
    def canon(name: str) -> str:
        """Normalize + apply the local WCVP crosswalk (tiers a-d)."""
        nn = normalize(name)
        return crosswalk.get(nn, nn)

    # Joined on base_image: GT keys carry GT_KEY_PREFIX and the box CSV does not, so
    # the stem used for the cache join is the join key here too.
    #
    # Imported here because crop_overlap imports ``normalize`` from this module.
    import crop_overlap
    crop_frames, crop_suspect = crop_overlap.build()

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
            # None means no box row at all, so coverage is unknown rather than
            # zero. The dominant name is canonicalised like the GT label.
            "crop_coverage": cov["coverage"] if cov else None,
            "crop_dominant": (canon(cov["dominant"])
                              if cov and cov["dominant"] else None),
        })

    sp_recs = [r for r in records if r["species_level"] and r["ranked"]]
    genus_recs = [r for r in records if not r["species_level"] and r["ranked"]]

    n_crop_joined = sum(1 for r in records if r["crop_coverage"] is not None)
    crop_admitted, crop_rejected = coverage_split(sp_recs, MIN_CROP_COVERAGE)
    _log_crop_gate(_log, records, sp_recs, crop_frames, crop_suspect,
                   n_crop_joined, crop_admitted, crop_rejected, MIN_CROP_COVERAGE)

    # ---------------- 6. one row per species ----------------
    corpus_canon = {canon(b) for b in corpus_raw}
    per_species = aggregate_per_species(sp_recs, corpus_norm, corpus_canon)

    return Health(
        gt_rows=gt_rows, split_rows=split_rows, split_of=split_of, predictions=predictions,
        maxk=maxk, joined=joined, missing_cache=missing_cache, crosswalk=crosswalk,
        corpus_norm=corpus_norm, corpus_canon=corpus_canon, gt_names=gt_names,
        tier_of_name=tier_of_name, tier_crowns=tier_crowns, records=records,
        sp_recs=sp_recs, genus_recs=genus_recs, per_species=per_species, canon=canon,
    )
