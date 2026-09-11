"""What ``labelling/assess_species.py`` found, read back with the standard library.

The script runs labelfirst and speciesfirst in their own virtualenv and writes
four JSON files into ``data/model_health/``. This module is the only reader.
Every file names the sha256 of the inputs it was computed from, and a file
whose inputs have since moved is stale: the loaders below still return what is
on disk, because measure.py must write its tables on a fresh clone, and the
*builder* refuses through ``complaint`` instead. The same split as
``queues.load_novelty`` and ``queues.novelty_complaint``, for the same reason:
a page that describes an assessment it is not using is worse than a page that
will not build.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
from collections import Counter

import core as hc

MODEL_HEALTH_DIR = os.path.join(hc.BASE, "model_health")
TRANSDUCTIVE_JSON = os.path.join(MODEL_HEALTH_DIR, "transductive.json")
DISAGREEMENT_JSON = os.path.join(MODEL_HEALTH_DIR, "disagreement.json")
REJECT_SWEEP_JSON = os.path.join(MODEL_HEALTH_DIR, "reject_sweep.json")
STATUS_JSON = os.path.join(MODEL_HEALTH_DIR, "status.json")
EMBEDDINGS_NPZ = os.path.join(hc.BASE, "embeddings_labelled", "embeddings.npz")
RERUN = "Re-run labelling/assess_species.py in the speciesfirst virtualenv"

# The species table's last column, in the page's words. The file carries
# labelfirst's own vocabulary; the page says what a botanist would do about it.
LIMIT_WORDS = {"sampling_limited": "more labels",
               "classifier_limited": "better model",
               "resolved": "no gap found"}

# Below this many embedded frames the verdict is about the draw, not the
# species: the rule votes over K_NEIGHBOURS=5 neighbours, so with half the
# frames held back a species needs about ten before its own kind can win a
# vote. The same floor as "Too few labels to judge", so the two columns cannot
# say "trust nothing here" and "better model" about one row.
LIMIT_MIN_FRAMES = hc.WELL_SAMPLED_MIN_N


def sha256_of(path: str) -> str:
    """Same digest ``labelfirst.io.queue.sha256_file`` writes, so the two
    sides of the check hash the same bytes the same way."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load(path: str) -> dict | None:
    """The file as written, or ``None`` when absent. Never a guess."""
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def complaint(path: str, doc: dict | None, *, gt_sha: str,
              embeddings_sha: str | None = None) -> str:
    """Why a page must not be built off this file, or ``""``.

    Missing, or computed from a ground truth (or an embedding file) other than
    the one on disk now. Either way the fix is one command, and the message
    names it.
    """
    if doc is None:
        return (f"{path} is missing, so the page cannot say what would help each "
                f"species. {RERUN}, or take the claim off the page.")
    inputs = doc.get("inputs", {})
    if inputs.get("gt_sha256") != gt_sha:
        return (f"{path} is stale: it was computed from a ground truth other than "
                f"{hc.GT_CSV} as it stands now. {RERUN}.")
    if embeddings_sha is not None and inputs.get("embeddings_sha256") != embeddings_sha:
        return (f"{path} is stale: it was computed from an embedding file other than "
                f"{EMBEDDINGS_NPZ} as it stands now. {RERUN}.")
    return ""


def limit_of(transductive: dict | None, species: str) -> tuple[str, str]:
    """The verdict for one species and how many draws agreed, both ``""`` when
    the file is absent, the species has no embedded frame, or it has fewer
    than ``LIMIT_MIN_FRAMES``. A blank is a blank: the page and the CSV both
    print it, so neither can read "unknown" as one of the three words."""
    if not transductive:
        return "", ""
    rec = transductive.get("per_species", {}).get(species)
    if not rec or rec["n_frames"] < LIMIT_MIN_FRAMES:
        return "", ""
    n_seeds = transductive["population"]["n_seeds"]
    return rec["limit"], f"{rec['seeds_agreeing']}/{n_seeds}"


# The two columns ``per_species_health.csv`` carries for it, in order.
LIMIT_COLUMNS = ("limit", "limit_agreement")


def limit_columns(transductive: dict | None, species: str) -> dict:
    """``limit_of`` as the two CSV cells."""
    return dict(zip(LIMIT_COLUMNS, limit_of(transductive, species)))


def limits_for(transductive: dict | None, per_species) -> dict:
    """``species -> (limit, agreement)`` for every row of the species table."""
    return {d["species"]: limit_of(transductive, d["species"]) for d in per_species}


def mechanism_of(disagreement: dict | None, key: str) -> str:
    """Why the label and the guess differ on one frame, in the file's words,
    or ``""`` when the file is absent or never saw the frame."""
    if not disagreement:
        return ""
    return disagreement.get("frames", {}).get(key, {}).get("mechanism", "")


def unassessed(disagreement: dict | None, keys) -> list:
    """Review-queue frames the file carries no verdict for: the queue has moved
    since the file was written, which no hash of the ground truth can see."""
    frames = (disagreement or {}).get("frames", {})
    return [k for k in keys if k not in frames]


# The sweep table's columns, in the order the page shows them. The CSV is the
# sidecar's rows and nothing else, so the page can link a file beside it. The
# new_flight_ columns are the same sweep with every flight whole in one fold.
REJECT_SWEEP_COLUMNS = ("max_set_size", "n_accepted", "n_frames", "accept_rate",
                        "accepted_accuracy", "new_flight_n_accepted",
                        "new_flight_accept_rate", "new_flight_accepted_accuracy")


def sweep_rows(sweep: dict | None) -> list[dict]:
    """The rows ``reject_sweep.csv`` carries, or none when the file is absent."""
    if not sweep:
        return []
    n = sweep["population"]["n_frames"]
    return [{"max_set_size": r["max_set_size"], "n_accepted": r["n_accepted"],
             "n_frames": n, "accept_rate": r["accept_rate"],
             "accepted_accuracy": r["accepted_accuracy"],
             "new_flight_n_accepted": g["n_accepted"],
             "new_flight_accept_rate": g["accept_rate"],
             "new_flight_accepted_accuracy": g["accepted_accuracy"]}
            for r, g in zip(sweep["rows"], sweep["grouped_rows"], strict=True)]


def write_label_review_queue(out_dir: str, review_rows, disagreement: dict | None) -> None:
    """Confident model/label disagreements, most confident first, each with the
    mechanism the disagreement file gives it, or blank when unassessed. Here
    beside the other sidecar-backed table only because measure.py is at the
    500-line rule; the rows are measure.py's."""
    with open(os.path.join(out_dir, "label_review_queue.csv"), "w", newline="",
              encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["global_key", "split", "gt_species", "predicted_species",
                    "confidence", "labelbox_url", "mechanism"])
        w.writerows([*r, mechanism_of(disagreement, r[0])] for r in review_rows)


def write_reject_sweep(out_dir: str, sweep: dict | None) -> None:
    """One row per plausible-name cap, copied from the sidecar. Header only
    when the sidecar is absent: the builder refuses before it reads this."""
    with open(os.path.join(out_dir, "reject_sweep.csv"), "w", newline="",
              encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(REJECT_SWEEP_COLUMNS))
        w.writeheader()
        w.writerows(sweep_rows(sweep))


def prepared(per_species, review) -> dict:
    """The fields the pages read: the four files, the columns derived from
    them, and one complaint per file that is missing or stale. ``review`` is
    the review queue as figures builds it, one record per frame."""
    gt_sha = sha256_of(hc.GT_CSV)
    emb_sha = sha256_of(EMBEDDINGS_NPZ) if os.path.exists(EMBEDDINGS_NPZ) else None
    docs = {name: load(path) for name, path in (
        ("transductive", TRANSDUCTIVE_JSON), ("disagreement", DISAGREEMENT_JSON),
        ("reject_sweep", REJECT_SWEEP_JSON), ("richness", STATUS_JSON))}
    complaints = [complaint(TRANSDUCTIVE_JSON, docs["transductive"], gt_sha=gt_sha,
                            embeddings_sha=emb_sha),
                  complaint(DISAGREEMENT_JSON, docs["disagreement"], gt_sha=gt_sha),
                  complaint(REJECT_SWEEP_JSON, docs["reject_sweep"], gt_sha=gt_sha,
                            embeddings_sha=emb_sha),
                  complaint(STATUS_JSON, docs["richness"], gt_sha=gt_sha)]
    if docs["reject_sweep"] and "grouped_rows" not in docs["reject_sweep"]:
        # The frame-by-frame rate is never printed without its new-flight twin.
        complaints.append(f"{REJECT_SWEEP_JSON} has no flight-grouped sweep, so the "
                          f"page would print only the rate that leans on near-copies "
                          f"from the same flight. {RERUN}.")
    keys = [r["global_key"] for r in review]
    missing = unassessed(docs["disagreement"], keys) if docs["disagreement"] else []
    if missing:
        complaints.append(
            f"{DISAGREEMENT_JSON} is stale: {len(missing)} of {len(keys)} review-queue "
            f"frames have no mechanism in it, so the queue moved since it was written. "
            f"{RERUN}.")
    return {**docs, "limits": limits_for(docs["transductive"], per_species),
            "review_mechanisms": Counter(mechanism_of(docs["disagreement"], k)
                                         for k in keys),
            "assessment_complaints": [m for m in complaints if m]}


def log_assessments(_log, transductive, disagreement, per_species, review_rows):
    """The run-log block for the two files measure.py copies columns from. Lives
    here rather than in run_log.py only because that file is at the 500-line
    rule; it prints and computes nothing the CSVs do not carry."""
    _log("--- ASSESSMENTS READ FROM data/model_health/ ---")
    if transductive is None:
        _log(f"  transductive.json : absent, limit column blank ({RERUN})")
    else:
        limits = [v for v, _ in limits_for(transductive, per_species).values()]
        named = sum(1 for v in limits if v)
        _log(f"  transductive.json : {named} of {len(limits)} species given a limit, "
             f"the rest under {LIMIT_MIN_FRAMES} embedded frames or unembedded")
        _log(f"    gt sha256 {transductive['inputs']['gt_sha256'][:12]}, "
             f"speciesfirst {transductive['library']['speciesfirst']}")
    if disagreement is None:
        _log(f"  disagreement.json : absent, mechanism column blank ({RERUN})")
    else:
        missing = unassessed(disagreement, (r[0] for r in review_rows))
        _log(f"  disagreement.json : {len(review_rows) - len(missing)} of "
             f"{len(review_rows)} review frames given a mechanism")
        _log(f"    gt sha256 {disagreement['inputs']['gt_sha256'][:12]}, "
             f"speciesfirst {disagreement['library']['speciesfirst']}")
    _log("")
