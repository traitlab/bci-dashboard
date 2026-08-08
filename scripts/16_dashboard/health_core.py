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
# INPUT PATHS (constants -- edit here if the sources move)
# --------------------------------------------------------------------------
REPO = "$REPO"
BASE = os.path.join(REPO, "output", "15_active_selection")

GT_CSV = os.path.join(BASE, "gt_dominant_taxon.csv")
SPLITS_CSV = os.path.join(BASE, "splits.csv")
CACHE_DIR = os.path.join(BASE, "new_ingest", "cache")

# Local warm WCVP resolution cache (built earlier from the GBIF-hosted WCVP
# dataset f382f0ce-323a-4091-bb9f-add557f3a9a2). Covers the ~249 BCI labels
# only. Set to None to disable match tier (d).
WCVP_CACHE_JSON = "$SPECIESFIRST/demo/interface_bundle_bci/wcvp_cache.json"

# global_key in the CSVs is "comb_<stem>.JPG"; cache file is "<stem>.JPG.json"
GT_KEY_PREFIX = "comb_"

CONF_BINS = [(0.0, 0.5), (0.5, 0.7), (0.7, 0.8), (0.8, 0.9), (0.9, 1.01)]
CONF_THRESHOLDS = [0.7, 0.8, 0.9]
SUPPORT_BUCKETS = [(1, 1, "1"), (2, 4, "2-4"), (5, 9, "5-9"),
                   (10, 24, "10-24"), (25, 10 ** 9, "25+")]
BUCKET_ORDER = [lab for _, _, lab in SUPPORT_BUCKETS]
WELL_SAMPLED_MIN_N = 10

# Send-first queue thresholds, from the 2026-08-05 call: the two
# things to focus labelling on are the long tail (species we don't have yet or
# the model does badly on) and low-confidence guesses on species it usually
# gets right. Below LOW_CONF the calibration table shows the first guess is
# right only ~38% of the time, which is "really not confident at all".
LOW_CONF = 0.5
WAIT_CONF = 0.8
# A species with at least this many labelled crowns and this measured top-1 is
# "usually right"; below HARD_MAX_TOP1 with enough crowns it is "hard".
RELIABLE_MIN_TOP1 = 0.90
HARD_MAX_TOP1 = 0.70
# A confident first guess that still disagrees with the botanist label is worth
# a second look: either the label or the model is wrong.
REVIEW_CONF = 0.8


# --------------------------------------------------------------------------
# Name handling
# --------------------------------------------------------------------------
_BCI_CODE = re.compile(r"-[A-Z0-9]{5,7}$")
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


def load_health(*, gt_csv=GT_CSV, splits_csv=SPLITS_CSV, cache_dir=CACHE_DIR,
                wcvp_cache=WCVP_CACHE_JSON, log: Optional[Callable[[str], None]] = None) -> Health:
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
    _log("  Read from scripts/15_active_selection/15xi_ingest_new_photos.py + config.yaml")
    _log("  + scripts/15_active_selection/sbatch_ingest.sh (the run that filled this cache):")
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
    _log("  string-strip of the Labelbox field label (see scripts/15_active_selection/")
    _log("  15a_export_gt_dominant_taxon.py). Hence trailing collection codes ('-QUARAS')")
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

    records = []
    for gk, stem, gt_name in joined:
        gt_c = canon(gt_name)
        records.append({
            "global_key": gk,
            "split": split_of.get(gk, ""),
            "gt_raw": gt_name,
            "gt": gt_c,
            "gt_strict": normalize(gt_name),
            "species_level": is_species_level(gt_c),
            "ranked": [(canon(b), s) for b, s in predictions[stem]],
            "ranked_strict": [(normalize(b), s) for b, s in predictions[stem]],
        })

    sp_recs = [r for r in records if r["species_level"] and r["ranked"]]
    genus_recs = [r for r in records if not r["species_level"] and r["ranked"]]

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
    )
