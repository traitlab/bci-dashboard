"""The queue page's embedded send rows and filtered download (F3)."""
import csv
import json
import re
import shutil
import subprocess
from types import SimpleNamespace

import pytest

HEADER = ["batch_id", "species_group", "global_key", "queue", "picked_by",
          "how_new_it_looks", "s3_uri", "labelbox_url", "data_row_id", "mission", "site", "growth_form"]
# A comma, a quote, a line break and a non-ASCII name: every case the serializer quotes.
ROWS = [
    ["1", "persicaria a", "k1", "long_tail", "queue", "0.700", "u1", "l1", "r1", "m1", "s1", "tree"],
    ["1", "control", "k2", "normal", "control", "", "", "", "", "", "", "unknown"],
    ["2", 'odd, "name"', "k3", "can_wait", "queue", "0.100", "u3", "l3", "r3", "m2", "s2", "liana"],
    ["2", "café\nline", "k4", "normal", "queue", "0.200", "u4", "l4", "r4", "m2", "s2", "liana"],
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
    assert "send_batch_1.csv --dry-run</pre>" in html


def test_next_batch_block_states_its_control_share(queue_filters, tables):
    html = queue_filters.next_batch_block(SimpleNamespace(verify_dir=str(tables)))
    assert "It stops at" not in html, "the waiting species is not at its cap"
    assert "About 15% of every batch is random control." in html


def _write_send(tmp_path, rows):
    with open(tmp_path / "send_batches.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(HEADER + ["group_by"])
        w.writerows([r + ["species"] for r in rows])
    return SimpleNamespace(verify_dir=str(tmp_path))


def _row(batch, sp, k, picked="queue"):
    return [str(batch), sp, k, "normal", picked, "0.5", "", "", "", "", "", ""]


def test_a_batch_short_because_every_waiting_species_is_capped_says_so(queue_filters, tmp_path):
    cap = queue_filters.queues.SPECIES_CAP
    rows = ([_row(1, "a", f"a{i}") for i in range(cap)]
            + [_row(2, "a", f"b{i}") for i in range(5)])
    html = queue_filters.next_batch_block(_write_send(tmp_path, rows))
    assert f"It stops at {cap} because every species still waiting already has {cap} photos" in html


def test_next_batch_block_is_empty_without_the_send_file(queue_filters, tmp_path):
    assert queue_filters.next_batch_block(SimpleNamespace(verify_dir=str(tmp_path))) == ""


def test_send_file_without_mission_and_site_columns_still_builds(queue_filters, tmp_path):
    (tmp_path / "send_batches.csv").write_text(
        "batch_id,species_group,global_key,queue\n1,a,k1,normal\n", encoding="utf-8")
    html = queue_filters.send_filters(SimpleNamespace(verify_dir=str(tmp_path)))
    assert 'id="f-mission"><option value="">all</option></select>' in html
    assert 'id="f-site"><option value="">all</option></select>' in html


def test_next_batch_block_prints_the_downloaded_file_and_how_annotators_find_it(queue_filters, tables):
    html = queue_filters.next_batch_block(SimpleNamespace(verify_dir=str(tables)))
    assert "python3 labelling/dispatch_round.py ~/Downloads/send_batch_1.csv --dry-run" in html
    assert "one batch named" in html
    # the download button names the file the command reads
    assert "'send_batch_'+b+'.csv'" in queue_filters._JS


def _count(queue_filters, tables, tmp_path, lo, hi):
    """Run the page script under node with a stub DOM; return the shown count text."""
    data = queue_filters.send_data(str(tables))
    script = tmp_path / "pick.js"
    script.write_text(
        "var data=" + json.dumps(data) + ";var els={};\n"
        "function E(){return {value:'',textContent:'',children:[],className:'',"
        "addEventListener:function(){},appendChild:function(){}}}\n"
        "['f-queue','f-species','f-mission','f-site','f-form','f-lo','f-hi','f-count','f-missions',"
        "'f-download'].forEach(function(i){els[i]=E()});\n"
        f"els['f-lo'].value='{lo}';els['f-hi'].value='{hi}';\n"
        "els['send-data']={textContent:JSON.stringify(data)};\n"
        "global.document={getElementById:function(i){return els[i]||null},"
        "createElement:E};\n"
        + queue_filters._JS + "\nconsole.log(els['f-count'].textContent);\n", encoding="utf-8")
    out = subprocess.run(["node", str(script)], capture_output=True, check=True, text=True).stdout
    return int(out.split()[0])


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_blank_confidence_passes_the_full_range_but_not_a_narrowed_one(queue_filters, tables, tmp_path):
    assert _count(queue_filters, tables, tmp_path, 0, 1) == 4  # k4 has no confidence, kept
    assert _count(queue_filters, tables, tmp_path, 0.8, 1) == 1  # only k3; k4 is dropped
    assert _count(queue_filters, tables, tmp_path, 0, 0.6) == 2  # k1, k2; k4 is dropped


def test_control_is_not_a_species_option(queue_filters, tables):
    html = queue_filters.send_filters(SimpleNamespace(verify_dir=str(tables)))
    species = re.search(r'id="f-species">(.*?)</select>', html, re.DOTALL).group(1)
    assert "persicaria a" in species and 'value="control"' not in species


def test_growth_form_is_a_filter_and_the_unfiltered_rows_keep_it(queue_filters, tables):
    html = queue_filters.send_filters(SimpleNamespace(verify_dir=str(tables)))
    form = re.search(r'id="f-form">(.*?)</select>', html, re.DOTALL).group(1)
    assert [v for v in re.findall(r'value="([^"]*)"', form) if v] == ["liana", "tree", "unknown"]
    assert "growth_form" in embedded(html)["header"]
