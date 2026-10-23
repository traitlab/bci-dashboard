"""The queue page's embedded send rows and filtered download (F3)."""
import csv
import json
import re
import shutil
import subprocess
from types import SimpleNamespace

import pytest

HEADER = ["batch_id", "species_group", "global_key", "queue", "picked_by",
          "how_new_it_looks", "image_url", "labelbox_url", "data_row_id", "mission", "site"]
# A comma, a quote, a line break and a non-ASCII name: every case the serializer quotes.
ROWS = [
    ["1", "persicaria a", "k1", "long_tail", "queue", "0.700", "u1", "l1", "r1", "m1", "s1"],
    ["1", "control", "k2", "normal", "control", "", "", "", "", "", ""],
    ["2", 'odd, "name"', "k3", "can_wait", "queue", "0.100", "u3", "l3", "r3", "m2", "s2"],
    ["2", "café\nline", "k4", "normal", "queue", "0.200", "u4", "l4", "r4", "m2", "s2"],
]
QUEUE_HEADER = ["queue", "global_key", "confidence", "predicted_species"]
CONF = {"k1": "0.1200", "k2": "0.5000", "k3": "0.9500"}  # k4 has no confidence


@pytest.fixture
def tables(tmp_path):
    for name, header, rows in (
            ("send_batches.csv", HEADER + ["group_by"], [r + ["species"] for r in ROWS]),
            ("send_first_queue.csv", QUEUE_HEADER,
             [["q", k, v, "x"] for k, v in CONF.items()])):
        with open(tmp_path / name, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(header)
            w.writerows(rows)
    return tmp_path


def embedded(html):
    m = re.search(r'<script type="application/json" id="send-data">(.*?)</script>', html, re.S)
    return json.loads(m.group(1).replace("<\\/", "</"))


def test_embedded_json_round_trips_to_the_csv(queue_filters, tables):
    data = embedded(queue_filters.send_filters(SimpleNamespace(verify_dir=str(tables))))
    with open(tables / "send_batches.csv", newline="", encoding="utf-8") as f:
        file_rows = list(csv.reader(f))
    assert [data["header"]] + data["rows"] == file_rows
    assert data["conf"] == ["0.1200", "0.5000", "0.9500", ""]


def test_confidence_is_not_a_download_column(queue_filters, tables):
    data = embedded(queue_filters.send_filters(SimpleNamespace(verify_dir=str(tables))))
    assert "confidence" not in data["header"]


def test_no_expert_label_reaches_the_embedded_rows(queue_filters, tables):
    html = queue_filters.send_filters(SimpleNamespace(verify_dir=str(tables)))
    assert "gt_species" not in html


def test_block_is_empty_without_the_send_file(queue_filters, tmp_path):
    assert queue_filters.send_filters(SimpleNamespace(verify_dir=str(tmp_path))) == ""
    assert queue_filters.send_filters(SimpleNamespace()) == ""


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_unfiltered_serializer_equals_the_file_byte_for_byte(queue_filters, tables, tmp_path):
    data = queue_filters.send_data(str(tables))
    script = tmp_path / "ser.js"
    script.write_text(queue_filters.CSV_JS + "\n"
                      "var d=JSON.parse(require('fs').readFileSync(process.argv[2],'utf8'));\n"
                      "process.stdout.write(toCsv(d.header,d.rows));\n", encoding="utf-8")
    (tmp_path / "d.json").write_text(json.dumps(data), encoding="utf-8")
    out = subprocess.run(["node", str(script), str(tmp_path / "d.json")],
                         capture_output=True, check=True).stdout
    assert out == (tables / "send_batches.csv").read_bytes()


def test_next_batch_block_states_size_download_and_dry_run_first(queue_filters, tables):
    html = queue_filters.next_batch_block(SimpleNamespace(verify_dir=str(tables)))
    assert "Next batch: 2 photos, grouped by species" in html
    assert "1 species group, 1 of them random control photos" in html
    assert 'data-batch="1"' in html and "Download batch 1 as CSV" in html
    assert "--batch 1 --dry-run</pre>" in html


def test_next_batch_block_is_empty_without_the_send_file(queue_filters, tmp_path):
    assert queue_filters.next_batch_block(SimpleNamespace(verify_dir=str(tmp_path))) == ""


def test_send_file_without_mission_and_site_columns_still_builds(queue_filters, tmp_path):
    (tmp_path / "send_batches.csv").write_text(
        "batch_id,species_group,global_key,queue\n1,a,k1,normal\n", encoding="utf-8")
    html = queue_filters.send_filters(SimpleNamespace(verify_dir=str(tmp_path)))
    assert 'id="f-mission"><option value="">all</option></select>' in html
    assert 'id="f-site"><option value="">all</option></select>' in html
