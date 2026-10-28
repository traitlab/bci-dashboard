"""The page build with the low-confidence share in every batch.

Since 2026-10-26 each batch gives its first places to the low-confidence queue,
one per confidence band (`queues.share_rows`). Two parts of the page build
predated that and broke on any pool where that queue is not empty: the page's
own packing left the confidence blank, and the build check wanted every species
in one run, which a share row picked ahead of its species' group is not.

    .venv/bin/pytest tests/test_low_conf_share_build.py
"""

import csv
from types import SimpleNamespace


def test_the_page_packs_a_pool_with_low_confidence_frames(figures):
    preds = {f"f{i}_zoom.JPG": [("species a", 0.1 + i / 40)] for i in range(12)}
    preds.update({f"g{i}_zoom.JPG": [("species b", 0.2)] for i in range(5)})
    h = SimpleNamespace(predictions=preds, labelled_stems=set(), canon=lambda s: s,
                        split_of={})
    per_species = [{"species": "species a", "top1_accuracy": 0.95},
                   {"species": "species b", "top1_accuracy": 0.95}]
    got = figures._queue(h, {"species a": 50, "species b": 50}, per_species)
    assert got["queue_counts"]["low_conf_known"] == 17
    assert got["n_batch1"] == 17


def test_the_check_accepts_a_share_row_apart_from_its_species(queues, history, tmp_path):
    cols = queues.SEND_FIRST_COLUMNS
    rows = []
    for i, (q, sp, conf) in enumerate([("long_tail", "a", "0.1")] * 4
                                      + [("low_conf_known", "a", "0.3"),
                                         ("low_conf_known", "b", "0.6"),
                                         ("low_conf_known", "a", "0.7")]):
        r = [""] * len(cols)
        r[cols.index("queue")], r[cols.index("global_key")] = q, f"k{i}"
        r[cols.index("predicted_species")], r[cols.index("confidence")] = sp, conf
        rows.append(r)
    batches = queues.chunk_send_batches(rows)
    # The share leads the batch, so species a appears, gives way to b, and comes back.
    queued = [b[1] for b in batches if b[4] == "queue"]
    assert queued[:3] == ["a", "b", "a"]
    with open(tmp_path / "q.csv", "w", newline="") as f:
        csv.writer(f).writerows([cols] + rows)
    with open(tmp_path / "send_batches.csv", "w", newline="") as f:
        csv.writer(f).writerows([queues.SEND_BATCH_COLUMNS + ["how_new_it_looks"]]
                                + [b + [""] for b in batches])
    assert "7 rows" in history.check_send_batches(str(tmp_path), str(tmp_path / "q.csv"), 7)
