"""The queue page over the catalog batches that labelling/catalog_batches.py writes.

frames.csv in the build tables switches the page to those files; without it
nothing changes. The build check recomputes the packing with catalog_batches.py
itself, so a hand-edited batch file stops the build.

    .venv/bin/pytest tests/test_catalog_queue.py
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

PRIORITY = "20260424_bcishannon_wptsendero_m3e"
OTHER = "20260402_bcishannon_wptjaco7524_m3e"


@pytest.fixture(scope="session")
def catalog_queue():
    from conftest import REPO, _on_path
    with _on_path(REPO / "dashboard"):
        import catalog_panels
        import catalog_queue
        yield SimpleNamespace(queue=catalog_queue, panels=catalog_panels)


@pytest.fixture
def tables(catalog_batches, tmp_path):
    """The four files catalog_batches.py writes, for a small pool: 40 priority
    frames, 130 rare-species frames over ten missions, 40 of one usual species
    guessed at low confidence."""
    pool, preds = {}, {}
    for i in range(170):
        mission = PRIORITY if i < 40 else OTHER.replace("7524", f"{7524 + i % 10}")
        key = f"rare{i:03d}.JPG"
        pool[key] = f"https://example.org/lefolab_drone_missions_wpt/{mission}/{key}"
        preds[key] = [(f"Rare sp{i}", 0.4)]
    for i in range(40):
        key = f"known{i:03d}.JPG"
        pool[key] = f"https://example.org/lefolab_drone_missions_wpt/{OTHER}/{key}"
        preds[key] = [("Good sp", 0.1 + i / 1000)]
    h = SimpleNamespace(canon=lambda n: n, per_species=[
        {"species": "Good sp", "n_labelled_frames": 100, "top1_accuracy": 0.95}])
    built = catalog_batches.build(pool, preds, h, set(), {PRIORITY})
    catalog_batches.write_files(tmp_path, built, pool)
    return tmp_path


def test_no_frames_file_is_the_main_pool(catalog_queue, tmp_path):
    assert catalog_queue.queue.load(str(tmp_path)) is None
    assert catalog_queue.queue.load("") is None


def test_the_figures_come_off_the_catalog_files(catalog_queue, tables):
    got = catalog_queue.queue.load(str(tables))
    cat = got["catalog"]
    assert got["n_unlab"] == 210 and cat["n_pool"] == 210
    assert got["n_batch1"] == 40 and cat["priority_batches"] == [1]
    assert got["n_batches"] == max(cat["batches"])
    assert got["thumbs"] == {} and got["selection_audit"] is None
    # example.org is no Arbutus host, so no s3_uri is filled.
    assert cat["n_s3"] == 0 and not cat["rarity"]


def test_the_check_passes_on_the_files_as_written(catalog_queue, tables):
    assert "210 catalog rows" in catalog_queue.queue.check(str(tables))


def test_a_batch_file_edited_by_hand_stops_the_build(catalog_queue, tables):
    path = tables / "send_batches.csv"
    lines = path.read_text(encoding="utf-8").splitlines()
    lines[1], lines[2] = lines[2], lines[1]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="not the packing"):
        catalog_queue.queue.check(str(tables))


def test_the_rule_names_the_priority_batch_and_the_mix(catalog_queue, tables):
    rule = catalog_queue.queue.batch_rule(catalog_queue.queue.load(str(tables))["catalog"])
    assert rule.startswith("Batch 1 holds the 40 queued frames of the priority missions")
    assert "From batch 2, each batch of at most 100 carries 15 random control" in rule
    assert "up to 20 photos from the low-confidence queue" in rule


def test_the_panel_says_nothing_of_the_main_pools_order(catalog_queue, tables):
    c = SimpleNamespace(**catalog_queue.queue.load(str(tables)), round_readout=None)
    html = catalog_queue.panels.p_send(c)
    assert "private Arbutus buckets" in html and "two names close" in html
    for gone in ("how new it looks", "least like anything labelled", "<img",
                 "About 15% of every batch", "ground truth", "—"):
        assert gone not in html


def test_the_check_replays_the_pins_the_batches_were_packed_with(catalog_batches,
                                                                 catalog_queue, tables):
    """A pinned batch sits where it was handed out, not where a fresh packing puts it."""
    frames = catalog_queue.queue._read(str(tables), "frames.csv")
    pool = {r["global_key"]: f"https://example.org/lefolab_drone_missions_wpt/{r['mission']}/"
            f"{r['global_key']}" for r in frames}
    preds = {k: [(f"Rare sp{k[4:7]}", 0.4) if k.startswith("rare") else ("Good sp", 0.1)]
             for k in pool}
    h = SimpleNamespace(canon=lambda n: n, per_species=[
        {"species": "Good sp", "n_labelled_frames": 100, "top1_accuracy": 0.95}])
    pins = [(2, f"known{i:03d}.JPG", "queue") for i in range(5)]
    built = catalog_batches.build(pool, preds, h, set(), {PRIORITY}, pins=pins,
                                  sent_nums={1})
    catalog_batches.write_files(tables, built, pool)
    assert "catalog rows" in catalog_queue.queue.check(str(tables))
