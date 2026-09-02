"""The vocabulary every other module works in.

Input paths, thresholds, name normalisation, and the helpers that turn counts
into page strings. Deterministic. ``health.py`` joins those files
into one ``Health``; ``queues.py`` decides what to send a botanist next.
"""

from __future__ import annotations

import csv
import datetime as _dt
import json
import os
import re
import unicodedata
from collections import defaultdict

# --- INPUT PATHS ---
# Derived from the checkout so a clone runs anywhere, each with an override:
#   BCI_DASHBOARD_REPO      checkout root            (default: one level up)
#   BCI_DASHBOARD_DATA      measurement inputs       (default: <repo>/data)
#   BCI_DASHBOARD_SNAPSHOTS dated snapshot store     (default: <repo>/snapshots)
#   BCI_DASHBOARD_TABLES    live measurement tables  (default: <repo>/build/tables)
#   BCI_WCVP_CACHE          WCVP resolution cache    (default: <repo>/data/wcvp_cache.json)
REPO = os.environ.get("BCI_DASHBOARD_REPO") or os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))
BASE = os.environ.get("BCI_DASHBOARD_DATA") or os.path.join(REPO, "data")

GT_CSV = os.path.join(BASE, "gt_dominant_taxon.csv")
SPLITS_CSV = os.path.join(BASE, "splits.csv")
CACHE_DIR = os.path.join(BASE, "predictions", "cache")

# global_key -> (data_row_id, project_id), from labelling/gt_from_export.py: the
# one offline source for a Labelbox deep link. Silent means the page says so.
DATA_ROW_IDS_CSV = os.path.join(BASE, "data_row_ids.csv")
LABELBOX_URL = "https://app.labelbox.com/projects/{project_id}/data-rows/{data_row_id}"

# Botanist verdicts on frames the review queue raised. Without a recorded ruling
# the queue raises the same frame forever. Tracked in git, or lost on a re-clone.
ADJUDICATIONS_CSV = os.path.join(BASE, "adjudications.csv")
# The one verdict that suppresses a frame. A label ruled wrong is fixed in
# Labelbox, where the next export carries the correction.
LABEL_CONFIRMED = "label_confirmed_prediction_wrong"

# Dated model-health-<date>/ folders: the trend history. Gitignored.
SNAPSHOT_DIR = os.environ.get("BCI_DASHBOARD_SNAPSHOTS") or os.path.join(REPO, "snapshots")

# Where measure.py writes the tables, and what a page cross-checks against. A
# snapshot is dated by the botanist's labels, so it goes stale the moment the
# code that writes a table changes; cross-checking it compares today's page
# with whatever the code did then. This directory always holds current output.
TABLES_DIR = os.environ.get("BCI_DASHBOARD_TABLES") or os.path.join(REPO, "build", "tables")

# Warm WCVP cache from GBIF dataset f382f0ce-323a-4091-bb9f-add557f3a9a2.
# Covers the ~249 BCI labels only. None disables match tier (d).
WCVP_CACHE_JSON = os.environ.get("BCI_WCVP_CACHE") or os.path.join(
    REPO, "data", "wcvp_cache.json")
if not os.path.exists(WCVP_CACHE_JSON):
    WCVP_CACHE_JSON = None

# global_key in the CSVs is "comb_<stem>.JPG"; cache file is "<stem>.JPG.json"
GT_KEY_PREFIX = "comb_"


def gt_provenance(gt_csv: str = GT_CSV) -> str:
    """One line naming the export the ground truth was merged from.
    Reads the sidecar ``labelling/gt_from_export.py`` writes at merge, falling
    back to the file's mtime, so every page agrees."""
    sidecar = os.path.splitext(gt_csv)[0] + ".provenance.txt"
    if os.path.exists(sidecar):
        with open(sidecar, encoding="utf-8") as f:
            return f.read().strip()
    mtime = _dt.date.fromtimestamp(os.path.getmtime(gt_csv)).isoformat()
    return f"Ground truth: {os.path.basename(gt_csv)}, dated {mtime}."

# How many names we ask Pl@ntNet for per photo (config.yaml identify_nb_results).
# A request setting, not a property of the model, and the number "the right name
# is in the list" is measured at.
N_CANDIDATES = 5

CONF_BINS = [(0.0, 0.5), (0.5, 0.7), (0.7, 0.8), (0.8, 0.9), (0.9, 1.01)]
CONF_THRESHOLDS = [0.7, 0.8, 0.9]
# The top band has no upper bound. Written as a number so the bands tile the
# integers with plain comparisons; readers test this name, not the literal.
NO_UPPER_BOUND = 10 ** 9
SUPPORT_BUCKETS = [(1, 1, "1"), (2, 4, "2-4"), (5, 9, "5-9"),
                   (10, 24, "10-24"), (25, NO_UPPER_BOUND, "25+")]
BUCKET_ORDER = [lab for _, _, lab in SUPPORT_BUCKETS]
WELL_SAMPLED_MIN_N = 10

# Send-first queue thresholds, applied in ``queues.py``. Below LOW_CONF the
# calibration table puts the first guess right only ~38% of the time.
LOW_CONF = 0.5
WAIT_CONF = 0.8
# A species with at least this many labelled crowns and this measured top-1 is
# "usually right"; below HARD_MAX_TOP1 with enough crowns it is "hard".
RELIABLE_MIN_TOP1 = 0.90
HARD_MAX_TOP1 = 0.70
# A confident first guess that still disagrees with the botanist label is worth
# a second look: either the label or the model is wrong.
REVIEW_CONF = 0.8

# Labels come from boxes drawn anywhere in the frame and predictions from a fixed
# centre crop, so a label can lie outside what the model was sent. Admitted only
# when the dominant species fills this much of the crop.
MIN_CROP_COVERAGE = 0.50
# Reported as a sweep, so the gate's effect on the headline is visible.
CROP_COVERAGE_SWEEP = (0.0, 0.3, 0.5, 0.8)


# --- Name handling ---
_BCI_CODE = re.compile(r"-[A-Z0-9]{5,7}$")
# Same idea before case folding, down to 4 characters ('-ANAE', '-HURC'). Upper
# case separates a code from a hyphenated epithet, so this needs the raw string.
_BCI_CODE_RAW = re.compile(r"-[A-Z0-9]{4,7}$")
_INFRA = re.compile(r"\b(var|subsp|ssp|f|cf|aff)\.?\s+\S+.*$", re.IGNORECASE)
_WS = re.compile(r"\s+")


def normalize(name: str) -> str:
    """Tier (b): normalized name, with no synonymy resolution.
    Strips accents, '_' to spaces, a trailing BCI collection code and
    infraspecific ranks ('var. grandiflora'), collapses whitespace, lowercases."""
    s = unicodedata.normalize("NFKD", name)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.replace("_", " ").strip()
    s = _BCI_CODE.sub("", s)
    s = _INFRA.sub("", s)
    return _WS.sub(" ", s).strip().lower()


def canonical_binomial(name):
    """Bare 'Genus species' from an authored accepted name.
    'Ocotea leptobotra (Ruiz & Pav.) Mez' -> 'Ocotea leptobotra'. None if the
    first two tokens are not a plain binomial. Same rule as
    speciesfirst.wcvp_export.canonical_binomial."""
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
def summarise(doc: str) -> str:
    """The first paragraph of a module docstring, as a terminal should read it.
    The rest is for someone with the file open: ``double backticks`` argparse
    prints literally, and a usage line it prints for itself."""
    return " ".join(doc.strip().split("\n\n")[0].replace("``", "").split())


# The four flags naming where the measurement inputs live. Names, defaults and
# help live here, so every command that reads them words them the same way.
INPUT_FLAGS = {
    "--gt": (GT_CSV, "botanist labels, one row per frame"),
    "--splits": (SPLITS_CSV, "which frames are held back for grading"),
    "--cache-dir": (CACHE_DIR, "folder of cached Pl@ntNet answers, one file per photo"),
    "--wcvp-cache": (WCVP_CACHE_JSON, "cached name crosswalk, used to match synonyms"),
}


def add_input_flags(p, *names: str, **help_overrides: str) -> None:
    """Add the shared input-path flags to a parser, worded the same every time."""
    for name in names or INPUT_FLAGS:
        default, help_ = INPUT_FLAGS[name]
        p.add_argument(name, default=default,
                       help=help_overrides.get(name.lstrip("-").replace("-", "_"), help_)
                            + f" (default: {os.path.relpath(default, REPO)})")


def read_csv_rows(path: str) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def labelbox_urls(path: str = DATA_ROW_IDS_CSV) -> dict[str, str]:
    """global_key -> Labelbox URL, where known.
    Reads the file the fetch step recorded. A missing file is an empty map, and
    the caller reports coverage."""
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
    A missing file is an empty set. Other verdicts are ignored, not rejected, so
    the file can record rulings this queue skips."""
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
    """The WCVP name crosswalk, as ``(renames, every_entry)``.

    ``renames`` maps a normalized input name to its normalized accepted binomial,
    and holds only the names WCVP moves. ``every_entry`` is the cache unfiltered,
    so the page can report how many were looked up."""
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


def canonicaliser(crosswalk: dict):
    """Normalize a name and apply the WCVP crosswalk, as one callable.
    The page builders and `score_confirmatory.py` both compare names from here:
    two definitions of the same species would split the frozen experiment from
    the pages without either being wrong."""
    def canon(name: str) -> str:
        nn = normalize(name or "")
        return crosswalk.get(nn, nn)

    return canon


def diagnose(row: dict) -> str:
    """Per-species status. First matching rule wins; order is the point.
    ``unreachable`` outranks all; no labelling helps. ``reliable`` outranks
    ``ranking``: >=90% needs no re-rank. ``unmeasured`` sits below ``ranking``,
    so a thin species already in the list counts as cheap."""
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


# The order above, as data, because the pages have to say it. The last two go by
# accuracy alone, so the tuple stops where the ordering stops mattering.
STATUS_PRECEDENCE = ("unreachable", "reliable", "ranking", "unmeasured")


# --- Crop coverage gate ---
def strip_collection_codes(name: str) -> str:
    """Drop every trailing BCI collection code, then normalize.
    Box labels carry two, the second shorter than normalize() recognizes
    ('-ANAE'). Strip before lowering: a lowered code reads as an epithet."""
    s, prev = (name or "").strip(), None
    while s != prev:
        prev = s
        s = _BCI_CODE_RAW.sub("", s).strip()
    return normalize(s)


def coverage_split(recs, min_coverage=MIN_CROP_COVERAGE):
    """(admitted, rejected) over records carrying a ``crop_coverage`` field.
    None means no measured geometry, and is rejected: the gate admits measured
    coverage only, never assumed. A crop dominated by a species other than the
    label is rejected too: the coverage measured there is that other tree's, so
    it says nothing about whether the label was inside the crop. Both tests
    together are the question ``next_batch.crop_verdict`` sends on, so the gate
    that is reported and the gate that picks work ask the same thing."""
    admitted, rejected = [], []
    for r in recs:
        c, dom = r.get("crop_coverage"), r.get("crop_dominant")
        ok = (c is not None and c >= min_coverage
              and (dom is None or dom == r["gt"]))
        (admitted if ok else rejected).append(r)
    return admitted, rejected


def coverage_gate_stats(recs, min_coverage=MIN_CROP_COVERAGE):
    """Headline numbers over the admitted subset of ``recs``.
    ``macro_top1`` averages per-species top-1 over admitted rows only, so its
    species set shrinks with the threshold. Report it beside the ungated macro
    average and ``n_admitted``."""
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
