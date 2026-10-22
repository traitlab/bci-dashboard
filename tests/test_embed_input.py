"""Every named frame gets a vector: the listing finds its URL, the stack keeps old rows."""

from __future__ import annotations

import json

import numpy as np
from conftest import REPO, _on_path, load

embed_input = load("_embed_input_under_test", REPO / "labelling" / "embed_input.py")
with _on_path(REPO / "predict"):
    embed = load("_embed_under_test", REPO / "predict" / "embed.py")


def test_named_rows_lists_each_named_frame_once_and_skips_ones_without_a_url(tmp_path, capsys):
    labels = tmp_path / "labels.csv"
    labels.write_text("global_key,taxon\nk1,A\nk2,B\nk1,A\nk3,C\n")
    inventory = tmp_path / "inv.jsonl"
    inventory.write_text(
        "\n".join(json.dumps(r) for r in [
            {"global_key": "k1", "row_data": "https://x/1.jpg"},
            {"global_key": "k2", "row_data": "https://x/2.jpg"},
            {"global_key": "k3"},
        ]) + "\n\n"
    )
    assert embed_input.named_rows(labels, inventory) == [
        ("k1", "https://x/1.jpg"), ("k2", "https://x/2.jpg")]
    assert "1 named frames have no photo URL" in capsys.readouterr().out


def test_named_flag_switches_the_default_output():
    assert embed_input.parse_args(["--named"]).out == embed_input.DEFAULT_NAMED_OUT
    assert embed_input.parse_args([]).out == embed_input.DEFAULT_OUT


def test_write_matrix_keeps_bundled_rows_and_lets_the_cache_win(tmp_path):
    dims = embed.EMBEDDING_DIMS
    cache, out = tmp_path / "cache", tmp_path / "out"
    cache.mkdir()
    out.mkdir()
    np.savez_compressed(out / "embeddings.npz", keys=np.array(["old", "both"]),
                        embeddings=np.zeros((2, dims), dtype=np.float32))
    for key in ("both", "new"):
        (cache / f"{embed.cache_name(key)}.json").write_text(
            json.dumps({"global_key": key, "embedding": [1.0] * dims}))
    (cache / "short.json").write_text(json.dumps({"global_key": "short", "embedding": [1.0]}))

    existing = embed.existing_matrix(out)
    assert set(existing) == {"old", "both"}
    path, n = embed.write_matrix(cache, out, existing)
    with np.load(path) as z:
        rows = dict(zip(z["keys"].tolist(), z["embeddings"]))
    assert n == 3 and set(rows) == {"old", "both", "new"}
    assert rows["old"].sum() == 0 and rows["both"].sum() == dims


def test_existing_matrix_is_empty_without_an_npz(tmp_path):
    assert embed.existing_matrix(tmp_path) == {}


def test_fetch_all_stops_once_the_time_budget_is_spent(tmp_path):
    rows = [{"global_key": "k", "image_url": "https://x/1.jpg"}]
    assert embed.fetch_all(rows, "key", "url", tmp_path, delay=0, test=False,
                           deadline=0) == (0, 0)


def test_an_export_fills_urls_the_inventory_predates_and_never_overrides_it(tmp_path):
    labels = tmp_path / "labels.csv"
    labels.write_text("global_key,taxon\ncomb_old.JPG,A\ncomb_new.JPG,B\n")
    inventory = tmp_path / "inv.jsonl"
    inventory.write_text(json.dumps({"global_key": "comb_old.JPG", "row_data": "https://inv/old.JPG"}) + "\n")
    export = tmp_path / "export.ndjson"
    export.write_text("".join(json.dumps({"data_row": {"global_key": f"m/{s}.JPG", "row_data": f"https://ex/{s}.JPG"}}) + "\n"
                              for s in ("old", "new")))
    assert embed_input.named_rows(labels, inventory, [export]) == [
        ("comb_old.JPG", "https://inv/old.JPG"), ("comb_new.JPG", "https://ex/new.JPG")]
    assert embed_input.parse_args(["--named", "--export", str(export)]).export == [export]
