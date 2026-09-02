"""The vocabulary every other module works in.

Where the input files are, what the thresholds are, how a species name is
normalised, and the small helpers that turn counts into the strings a page
prints. Deterministic, no network, and nothing here reads a file it was not
handed a path to.

Reading those files and joining them into one ``Health`` is ``health.py``.
Deciding what to send a botanist next is ``queues.py``.
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
# labelling/gt_from_export.py. The one offline source for a Labelbox deep link:
# a data row opens only inside a project it belongs to, and the export states
# both halves. Where it is silent the page reports the gap, never guesses.
DATA_ROW_IDS_CSV = os.path.join(BASE, "data_row_ids.csv")
LABELBOX_URL = "https://app.labelbox.com/projects/{project_id}/data-rows/{data_row_id}"

# Botanist verdicts on frames the review queue raised. The prediction never
# changes, so without a recorded ruling the queue raises the same frame
# forever. Tracked in git: an untracked verdict is lost on the next clone.
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

# How many names we ask Pl@ntNet for per photo (config.yaml
# identify_nb_results). A request setting, not a property of the model, and the
# number "the right name is in the list" is measured at. Here rather than in
# figures.py so the measurement, the cache guard and the page wording all read
# one value.
N_CANDIDATES = 5

CONF_BINS = [(0.0, 0.5), (0.5, 0.7), (0.7, 0.8), (0.8, 0.9), (0.9, 1.01)]
CONF_THRESHOLDS = [0.7, 0.8, 0.9]
# The top band has no upper bound. It is written as a number so the bands
# can tile the integers with plain comparisons; anything reading a band back
# out, like explain._band_words turning it into "25 or more frames", tests
# against this name rather than retyping the number.
NO_UPPER_BOUND = 10 ** 9
SUPPORT_BUCKETS = [(1, 1, "1"), (2, 4, "2-4"), (5, 9, "5-9"),
                   (10, 24, "10-24"), (25, NO_UPPER_BOUND, "25+")]
BUCKET_ORDER = [lab for _, _, lab in SUPPORT_BUCKETS]
WELL_SAMPLED_MIN_N = 10

# Send-first queue thresholds, applied in ``queues.py``. Labelling buys most on
# the long tail and on weak guesses at usually-right species. Below LOW_CONF the calibration table puts
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
def summarise(doc: str) -> str:
    """The first paragraph of a module docstring, as a terminal should read it.

    The rest is written for someone with the file open: ``double backticks``,
    which argparse prints literally, and the usage line it prints for itself.
    """
    return " ".join(doc.strip().split("\n\n")[0].replace("``", "").split())


# The four flags naming where the measurement inputs live. Every command that
# reads them offers the same four, so the names, defaults and help live here and
# each command asks for the ones it uses.
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
    """The WCVP name crosswalk, as ``(renames, every_entry)``.

    ``renames`` maps a normalized input name to its normalized accepted
    binomial, and holds only the names WCVP moves. ``every_entry`` is the cache
    unfiltered: the page reports how many were looked up, not only how many
    changed.
    """
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

    Both the page builders and `score_confirmatory.py` compare names this way,
    and each used to define the closure itself. Two definitions of what counts
    as the same species is the one difference that would make the frozen
    experiment and the pages disagree without either being wrong.
    """
    def canon(name: str) -> str:
        nn = normalize(name or "")
        return crosswalk.get(nn, nn)

    return canon


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


# The order above, as data, because the pages have to say it: a reader sorting
# on the status column otherwise meets one-frame species tagged as cheap work
# with nothing explaining why. The last two statuses are decided by accuracy
# alone, so the tuple stops where the ordering stops mattering. A test walks
# ``diagnose`` to check that.
STATUS_PRECEDENCE = ("unreachable", "reliable", "ranking", "unmeasured")


# --- Crop coverage gate ---
def strip_collection_codes(name: str) -> str:
    """Drop every trailing BCI collection code, then normalize.

    Box labels carry two, and the second can be shorter than normalize()
    recognizes ('-ANAE'). Strip first: codes are upper case, and a lowered one
    cannot be told from a hyphenated epithet.
    """
    s, prev = (name or "").strip(), None
    while s != prev:
        prev = s
        s = _BCI_CODE_RAW.sub("", s).strip()
    return normalize(s)


def coverage_split(recs, min_coverage=MIN_CROP_COVERAGE):
    """(admitted, rejected) over records carrying a ``crop_coverage`` field.

    No measured geometry means None, which is rejected: the gate admits
    measured coverage only, never assumed.
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
