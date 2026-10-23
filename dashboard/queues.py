"""Which unlabelled photos to send a botanist next, and in what order.

One decision procedure on top of `core.py`'s shared vocabulary: the four
send-first queues, their order, and how the queue is packed into batches one
sitting can review. `measure.py` and `figures.py` both go through
`send_first_rows`, so the file and the page cannot disagree. They must also go
through `load_novelty` for the same reason: two readings of the ordering file
would put the page and the CSV in a different order, which aborts the build.

Thresholds stay in `core` because `run_log.py` and both page builders read them.
"""

from __future__ import annotations

import csv
import json
import os
import random
import re
from collections import Counter, defaultdict

from core import (
    HARD_MAX_TOP1,
    LOW_CONF,
    RELIABLE_MIN_TOP1,
    WAIT_CONF,
    WELL_SAMPLED_MIN_N,
)


# Queue names, in the order a botanist should work through them.
QUEUE_ORDER = ["long_tail", "low_conf_known", "normal", "can_wait"]
# The bottom queue, what the wait rule pushes down. Nobody works it, so the
# page prints it as a record, not as a sheet of frames to open.
WAIT_QUEUE = QUEUE_ORDER[-1]

# send_first_queue.csv's columns, in order. `measure.py` writes the header and
# `chunk_send_batches` below reads rows by position, so the order is named once.
#
# `batch_id` is last and filled in after the batching runs, so a queued frame's
# batch is read off its own row instead of by re-running the batcher.
#
# `how_new_it_looks` sits beside the rank it explains: the distance from the
# photo to the nearest labelled one, which is what the rank was sorted on.
# Three decimals, since the file is read by people.
SEND_FIRST_COLUMNS = ["queue", "global_key", "split", "predicted_species", "confidence",
                      "species_labelled_crowns", "species_top1_accuracy", "novelty_rank",
                      "how_new_it_looks", "batch_id"]
# Written after the columns above, looked up per frame at write time like the
# batch file's links, so the packing and its identity check do not see it.
SEND_FIRST_LOOKUP_COLUMNS = ["data_row_id", "mission", "site"]
SEND_FIRST_HEADER = SEND_FIRST_COLUMNS + SEND_FIRST_LOOKUP_COLUMNS
# send_batches.csv's columns, likewise: returned in this order, written as that header.
SEND_BATCH_COLUMNS = ["batch_id", "species_group", "global_key", "queue", "picked_by"]
# The same distance on the batch file, since that is the file the botanist
# opens and the one place the question "why is this row first" gets asked.
# Looked up per frame at write time like the links below, for the same reason.
SEND_BATCH_LOOKUP_COLUMNS = ["how_new_it_looks"]
# Two more columns the file carries and the packing does not decide. They are
# looked up per frame at write time, so `chunk_send_batches` stays a pure
# function of the queue and `history.check_send_batches` can keep comparing its
# output to the file column by column. The header is the two lists joined.
#
# Both links, not one. `image_url` opens for anyone with a browser and covers
# every row; `labelbox_url` is the only one that shows which crown is asked about.
#
# `data_row_id` is the id inside `labelbox_url`, parsed by `core.data_row_id`,
# which for a legacy-mode link is the row in the project the frame was labelled
# in. A frame with no link takes its id from the dispatch dataset inventory
# (`core.send_row_id`), so it is empty only for a photo that dataset lacks.
#
# `mission` and `site` say where the frame was flown, off the inventory; blank
# for a frame it does not name.
#
# `growth_form` is the predicted species' growth form off input/growth_form.csv,
# `unknown` where the file does not name it (a control row carries its own prediction's).
#
# `group_by` is last and the same on every row: how the file was packed
# ("species" or "rank", see `GROUP_BY`), so a batch's mode can be read off it
# when Labelbox time per label is compared across batches.
SEND_BATCH_LINK_COLUMNS = ["image_url", "labelbox_url", "data_row_id", "mission", "site",
                           "growth_form", "group_by"]
SEND_BATCH_HEADER = SEND_BATCH_COLUMNS + SEND_BATCH_LOOKUP_COLUMNS + SEND_BATCH_LINK_COLUMNS

# No more than this many crowns per Labelbox batch, one botanist session's worth.
# Overridable because the right number is the labelling team's call, so
# changing it should not be a source edit.
# `measure.py` writes the packing and `history.check_send_batches` verifies it
# against this same constant, so a value changed between those two steps fails
# the build rather than shipping a page that describes a packing nobody ran.
# It also sets the random control, `control_size` rows of every batch.
def _batch_size_from_env(raw: str | None, default: int = 100) -> int:
    """``BCI_BATCH_SIZE``, or the default when it is unset or empty.

    Rejected loudly rather than coerced: a batch size that silently fell back
    to 100 because of a typo would repartition the queue against a number
    nobody chose, and the page would then describe that partition as intended.
    """
    if raw is None or not raw.strip():
        return default
    try:
        n = int(raw.strip())
    except ValueError:
        raise ValueError(f"BCI_BATCH_SIZE must be a whole number, got {raw!r}") from None
    if n < 1:
        raise ValueError(f"BCI_BATCH_SIZE must be at least 1, got {n}")
    return n


BATCH_SIZE = _batch_size_from_env(os.environ.get("BCI_BATCH_SIZE"))

# At most this many photos of one predicted species in any one batch. A species
# with more waits for the next batch, at the same place in the queue, so one
# common species cannot fill a sitting. Control photos are not counted.
SPECIES_CAP = 20

# How rows are packed into batches. "species" keeps each species together at the
# rank of its best photo; "rank" is strict queue order in fixed-size chunks.
# Which one annotators work faster in is untested, so species stays the default.
GROUP_BYS = ("species", "rank")
# How each mode reads in a sentence on a page.
GROUP_PHRASE = {
    "species": f"each species kept together, at most {SPECIES_CAP} photos of one species per batch",
    "rank": f"in strict rank order, at most {SPECIES_CAP} photos of one species per batch"}


def _group_by_from_env(raw: str | None, default: str = "species") -> str:
    """``BCI_GROUP_BY``, or the default when unset or empty. Rejected loudly,
    like the batch size: a typo must not silently change how batches are cut."""
    if raw is None or not raw.strip():
        return default
    if raw.strip() not in GROUP_BYS:
        raise ValueError(f"BCI_GROUP_BY must be one of {GROUP_BYS}, got {raw!r}")
    return raw.strip()


GROUP_BY = _group_by_from_env(os.environ.get("BCI_GROUP_BY"))

# The share of every batch drawn at random from the photos not sent yet instead
# of from the head of the queue: the random control. Each closed round then
# compares the queue's picks with random ones drawn from the same pool, which
# nothing else measures. 15% of a hundred is fifteen photos a batch, so most of
# the botanist hours the queue saves are still saved.
CONTROL_FRACTION = 0.15
# Fixed, so two runs of measure.py write the same file. Changing it draws a
# different control, which is a new comparison, not a correction.
CONTROL_SEED = 20260903
# What a control row carries in `species_group`. Not a species, and it cannot
# collide with one: every species name here is a binomial.
CONTROL_GROUP = "control"

# The place in the order a frame with no vector takes: after every ranked frame
# of its queue, where the frames behind it keep today's confidence order. Bigger
# than any rank the ranker can assign, since the pool is four figures.
NO_NOVELTY = 10 ** 9

# The sidecar `labelling/rank_queue.py` writes beside the ordering file: the
# run record labelfirst lays down next to any queue it saves, `<csv>.run.json`.
# The ranker runs outside bin/refresh.sh, so this file is the only record of
# when the ordering was last rebuilt and against what. The older hand-written
# `.provenance.txt`, with a `rows=N` on each source line, is still read one
# release on, so a checkout ranked before the switch keeps its date.
NOVELTY_RUN_SUFFIX = ".run.json"
NOVELTY_PROVENANCE_SUFFIX = ".provenance.txt"
_PROVENANCE_ROWS = re.compile(r"\brows=(\d+)\b")
# The distance column the ordering file carries beside the rank.
NOVELTY_DISTANCE_COLUMN = "distance_to_nearest_labelled"


def load_novelty(path: str) -> dict:
    """``global_key`` -> how unlike the labelled frames a photo looks, 1 first.

    Written by ``labelling/rank_queue.py``, which needs numpy and so cannot run
    here. An absent file is the normal state of a fresh clone and of any
    checkout before the embeddings are fetched: it returns ``{}``, every frame
    ties, and the order falls back to the unranked order.
    A row whose rank is not a whole number is dropped rather than guessed at.
    """
    if not os.path.exists(path):
        return {}
    out = {}
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            key, rank = row.get("global_key"), row.get("novelty_rank")
            if not key or rank is None:
                continue
            try:
                out[key] = int(rank)
            except ValueError:
                continue
    return out


def how_new(distance: dict, key: str) -> str:
    """The distance column as written: three decimals, or blank for a frame the
    ordering file never scored. Blank and not zero, since zero is a photo that
    looks exactly like a labelled one."""
    return f"{distance[key]:.3f}" if key in distance else ""


def load_novelty_distance(path: str) -> dict:
    """``global_key`` -> how far the photo is from the nearest labelled one, as
    the ordering file wrote it. Same forgiveness as ``load_novelty``: an absent
    file, or a row without a usable number, is simply not in the map."""
    if not os.path.exists(path):
        return {}
    out = {}
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            key, d = row.get("global_key"), row.get(NOVELTY_DISTANCE_COLUMN)
            if not key or d is None:
                continue
            try:
                out[key] = float(d)
            except ValueError:
                continue
    return out


def novelty_provenance(path: str) -> dict:
    """What the ordering file was built from: written date, anchors, pool, and
    the hash and library version that make a re-run tell apart from a copy.

    ``labelling/rank_queue.py`` writes the sidecar beside the CSV because the
    ranker runs outside ``bin/refresh.sh``, in its own virtualenv, and nothing
    else on disk records when it last ran. Every value is ``None`` when the
    sidecar is absent or does not carry that field: a missing number is
    reported as missing, never guessed at from the CSV, because the two counts
    a reader wants (how many labelled frames anchored the ranking, how many
    photos were ranked against them) are properties of the embedding files and
    not of this CSV's row count.

    The run record is read first. The hand-written text sidecar is the fallback
    for a checkout ranked before the record existed, and carries no hash.
    """
    out: dict = {"written": None, "anchors": None, "pool": None,
                 "sha": None, "anchor_sha": None, "library": None, "unembedded": None}
    record = path + NOVELTY_RUN_SUFFIX
    if os.path.exists(record):
        with open(record, encoding="utf-8") as f:
            try:
                rec = json.load(f)
            except ValueError:
                rec = {}
        if isinstance(rec, dict):
            extra = rec.get("extra") if isinstance(rec.get("extra"), dict) else {}
            out["written"] = extra.get("written") or (rec.get("timestamp_utc") or "")[:10] or None
            out["anchors"] = _whole(rec.get("n_labeled"))
            out["pool"] = _whole(rec.get("n_pool"))
            out["sha"] = rec.get("embedding_sha256") or None
            out["anchor_sha"] = extra.get("anchor_sha256") or None
            out["unembedded"] = _whole(extra.get("named_without_embedding"))
            out["library"] = rec.get("library_version") or None
        return out
    sidecar = os.path.splitext(path)[0] + NOVELTY_PROVENANCE_SUFFIX
    if not os.path.exists(sidecar):
        return out
    with open(sidecar, encoding="utf-8") as f:
        for line in f:
            role, sep, rest = line.partition(":")
            if not sep:
                continue
            role = role.strip()
            if role == "written":
                out["written"] = rest.strip() or None
            elif role in ("anchors", "pool"):
                found = _PROVENANCE_ROWS.search(rest)
                if found:
                    out[role] = int(found.group(1))
    return out


def _whole(v) -> int | None:
    """An int, or None for anything that is not one. A count read off a record
    is either a whole number or not there."""
    return v if isinstance(v, int) and not isinstance(v, bool) else None


def novelty_complaint(path: str, n_ranked: int, n_unlab: int) -> str:
    """Why a page must not be built off this ordering file, or ``""``.

    ``queues.load_novelty`` is deliberately forgiving: an absent file is the
    normal state of a fresh clone, and it returns ``{}`` so the queue still
    comes out in confidence order. That forgiveness is the hazard. The ranker
    is not in ``bin/refresh.sh``, so the file can go missing between two builds
    without anything else changing, and the page goes on saying the photo least
    like everything already labelled comes first while the order behind that
    sentence has silently reverted to the one it replaced.

    So the loader keeps falling back and the *builder* refuses instead. A page
    that describes an ordering it is not using is worse than a page that will
    not build: the first is read and believed, the second is fixed.
    """
    if not os.path.exists(path):
        return (f"{path} is missing, so every frame ties on novelty and the queue "
                f"has silently fallen back to confidence order, which is not the "
                f"order this page describes. Re-run labelling/rank_queue.py, or "
                f"take the ordering claim off the page.")
    if n_unlab and not n_ranked:
        return (f"{path} is present but ranks none of the {n_unlab:,} queued frames, "
                f"so the queue is in confidence order while the page describes an "
                f"embedding order. The file is stale against this pool: re-run "
                f"labelling/rank_queue.py.")
    return ""


def control_size(batch_size: int = BATCH_SIZE,
                 fraction: float = CONTROL_FRACTION) -> int:
    """How many of each batch are the random control rather than queue work.

    The page quotes this and the batcher reserves room for it, so it is worked
    out once. Never the whole batch: every batch has queue work to do too.
    """
    if not 0 <= fraction < 1:
        raise ValueError(f"control fraction must be in [0, 1), got {fraction}")
    n = round(batch_size * fraction)
    return 0 if n < 1 else min(n, batch_size - 1)


def chunk_send_batches(queue_rows: list, batch_size: int = BATCH_SIZE,
                       control_fraction: float = CONTROL_FRACTION,
                       group_by: str = GROUP_BY, seed: int = CONTROL_SEED,
                       species_cap: int = SPECIES_CAP) -> list:
    """Species-grouped, priority-first batches over an already-ordered
    ``queue_rows`` (send_first_queue.csv order). Each species is visited once,
    at its highest-priority row; its rows travel together, packed whole until
    the next would overflow the batch, which then opens the next one. A species
    larger than the room a batch has is cut at that room.

    No batch holds more than ``species_cap`` queue rows of one predicted
    species. The rows past it keep their place in the queue, in their rank
    order: the packer skips that species for the rest of the batch, keeps
    filling from later groups, and the skipped rows open the next batch.

    ``group_by="rank"`` instead cuts the queue in strict rank order into
    fixed-size chunks, each row labelled with its own species.

    Each batch's queue rows are packed first, then the batch takes a random
    control sized from them: about ``control_fraction`` of the batch total, at
    most ``control_size`` rows. The control is the next photos not sent yet in
    one seeded shuffle of the whole pool, outside the batch's own rows, so it
    is a uniform draw from what is left, and it rides at the end of the batch as
    one block. When the pool runs dry (the last batch) the rest comes out of the
    batch's own rows, and a batch always keeps one queue photo. The result is
    still a repartition of the queue: control photos move forward, are never
    added, and no photo is sent twice.
    """
    if batch_size < 1:
        raise ValueError(f"batch_size must be at least 1, got {batch_size}")
    if species_cap < 1:
        raise ValueError(f"species_cap must be at least 1, got {species_cap}")
    if group_by not in GROUP_BYS:
        raise ValueError(f"group_by must be one of {GROUP_BYS}, got {group_by!r}")
    queue_at = SEND_FIRST_COLUMNS.index("queue")
    key_at = SEND_FIRST_COLUMNS.index("global_key")
    species_at = SEND_FIRST_COLUMNS.index("predicted_species")
    n_control = control_size(batch_size, control_fraction)
    cap = batch_size - n_control  # room each batch keeps for queue rows

    order: list[str] = []
    by_species: dict[str, list[int]] = defaultdict(list)
    for i, row in enumerate(queue_rows):
        sp = row[species_at]
        if sp not in by_species:
            order.append(sp)
        by_species[sp].append(i)
    groups = [(sp, by_species[sp]) for sp in order]
    if group_by == "rank":
        # One-row groups through the same packing loop: rank order, no splitting.
        groups = [(row[species_at], [i]) for i, row in enumerate(queue_rows)]

    n = len(queue_rows)
    draw = random.Random(seed).sample(range(n), n) if n_control else []
    taken: set[int] = set()
    batches: list = []
    pending = list(groups)
    batch_id = 0
    while pending:
        # Pack the queue rows first: the control is sized from what the batch holds.
        pieces: list = []
        held = 0
        held_by: Counter = Counter()
        j = 0  # a capped species is skipped, not popped: it stays for the next batch
        while j < len(pending):
            sp, idx = pending[j]
            rows = [i for i in idx if i not in taken]
            if not rows:
                pending.pop(j)
                continue
            room_sp = species_cap - held_by[sp]
            if room_sp <= 0:
                j += 1
                continue
            take = rows[:room_sp]
            if held and held + len(take) > cap:
                break
            # An oversized species fills the batch; the rest opens the next one.
            take = take[:cap - held]
            if len(take) < len(rows):
                pending[j] = (sp, rows[len(take):])
            else:
                pending.pop(j)
            pieces.append((sp, take))
            held += len(take)
            held_by[sp] += len(take)
            taken.update(take)
        if not pieces:
            break
        batch_id += 1
        control: list[int] = []
        if n_control:
            # Random photos not sent yet, outside this batch. The share is of the
            # batch total, queue / (1 - fraction) control rows, at most n_control.
            want = min(n_control, max(1, round(held * control_fraction / (1 - control_fraction))))
            pool = [i for i in draw if i not in taken]
            control = pool[:want]
            if len(pool) < want:
                # The pool ran dry (last batch): the rest of the control comes out of
                # this batch's own rows, in the same draw, and the share is of what remains.
                total = held + len(pool)
                size = min(total - 1, max(1, round(control_fraction * total)))
                own = {i for _, rows in pieces for i in rows}
                control = (pool + [i for i in draw if i in own])[:max(size, 0)]
            taken.update(control)
        drawn = set(control)
        for sp, rows in pieces:
            batches.extend([batch_id, sp, queue_rows[i][key_at], queue_rows[i][queue_at], "queue"]
                           for i in rows if i not in drawn)
        batches.extend([batch_id, CONTROL_GROUP, queue_rows[i][key_at],
                        queue_rows[i][queue_at], "control"] for i in sorted(control))
    return batches


def with_batch_ids(queue_rows: list, batch_rows: list) -> list:
    """``queue_rows`` again, each row carrying the batch it was packed into.

    The batcher is the only thing that knows the answer, so the column is filled
    from its output rather than derived a second time. Deriving it twice is how
    two files that are supposed to agree stop agreeing.

    Every queued frame is packed exactly once, so a frame the batcher never
    named, or named twice, means the packing and the queue have come apart and
    there is no honest value to write. That is a build failure, not a blank
    cell: a blank one would be read as "not scheduled yet".
    """
    key_at = SEND_FIRST_COLUMNS.index("global_key")
    batch_at = SEND_BATCH_COLUMNS.index("batch_id")
    of_key: dict[str, int] = {}
    for b in batch_rows:
        key = b[SEND_BATCH_COLUMNS.index("global_key")]
        if key in of_key:
            raise ValueError(f"{key} is in more than one send batch")
        of_key[key] = b[batch_at]
    missing = [r[key_at] for r in queue_rows if r[key_at] not in of_key]
    if missing:
        raise ValueError(f"{len(missing)} queued frames were never packed into a "
                         f"batch, first {missing[0]}")
    # Set by position, and short rows padded first: the batcher runs on rows
    # that do not have the column yet, and verify_snapshot re-packs rows read
    # back out of the file that do. Both come through here and both leave the
    # same width as the header.
    at = SEND_FIRST_COLUMNS.index("batch_id")
    out = []
    for r in queue_rows:
        row = list(r) + [""] * (len(SEND_FIRST_COLUMNS) - len(r))
        row[at] = of_key[r[key_at]]
        out.append(row)
    return out


def queue_of_prediction(pred: str, conf: float, support: dict, top1: dict) -> str:
    """Which queue an unlabelled crown lands in, from its top prediction alone.

    ``support``: labelled-crown count per species. ``top1``: measured accuracy
    per species. Absent from both means never labelled. First rule wins, so a
    weak prediction on a rare species stays in the long tail.
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


def send_first_rows(predictions, joined_stems, canon, support, top1,
                    novelty=None, key_prefix="", splits=None, sent=()) -> tuple:
    """Every unlabelled frame's queue, in the order send_first_queue.csv writes.

    Returns ``([(queue, stem, species, confidence, novelty_rank), ...],
    n_no_answer, held_out)``. Order is queue first, then least like the frames
    already labelled and those ranked above it, then least confident, then the
    stem. Confidence says nothing about a species with almost no labels, and on the later "tele"
    naming batch it is not trustworthy at all, so what a photo looks like leads and
    confidence breaks the tie. A frame the model answered nothing for is
    counted, not queued.

    ``novelty`` is the map ``load_novelty`` returns, keyed the way the CSV
    writes a photo, hence ``key_prefix``. Empty, or missing a frame, and that
    frame sorts to the back of its queue in confidence order: the behaviour
    before there were any vectors, and the way to undo this ordering.

    ``splits`` is ``global_key -> split`` from ``data/splits.csv``, keyed the
    same way. A frame carrying a split is an evaluation frame and is held out
    of the queue rather than queued: it is one of the frames the per-species
    statuses and the wait rule are read off, and sending it back for labelling
    puts a botanist's new answer into the set those numbers are measured on.
    ``held_out`` counts what was dropped, by split, because a frame that
    vanishes from a work queue with nothing said is how a count moves and
    nobody can explain why. ``None`` holds nothing out, which is the behaviour
    a caller with no splits file gets.

    ``sent`` is the keys in the round ledgers, keyed like ``novelty``: sent to
    Labelbox and not labelled yet, so they are not the next thing to send.
    """
    novelty = novelty or {}
    splits = splits or {}
    rows, n_no_answer = [], 0
    held_out: Counter = Counter()
    for stem in sorted(predictions):
        if stem in joined_stems or key_prefix + stem in sent:
            continue
        split = splits.get(key_prefix + stem, "")
        if split:
            held_out[split] += 1
            continue
        ranked = [(canon(name), score) for name, score in predictions[stem]]
        if not ranked:
            n_no_answer += 1
            continue
        pred, conf = ranked[0]
        rows.append((queue_of_prediction(pred, conf, support, top1), stem, pred, conf,
                     novelty.get(key_prefix + stem, NO_NOVELTY)))
    rows.sort(key=lambda r: (QUEUE_ORDER.index(r[0]), r[4], r[3], r[1]))
    return rows, n_no_answer, held_out
