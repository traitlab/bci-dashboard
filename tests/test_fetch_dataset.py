"""The checks `labelling/fetch_dataset.py` runs before it pages anything.

Two inventories now live in `data/`, one per Labelbox dataset, and
`dashboard/core.py` reads both by name. The file name is therefore the only
record of which dataset a dump holds, which makes the default `--out` a place a
second dataset must never land: it would replace one inventory with another,
every deep link only the first one knows would quietly change project, and no
gate downstream would see it. So the wrong pairing is a stop here.

Nothing in this file makes a network call or reads a credential.
"""

from __future__ import annotations

import pytest

CONFIGURED = "cmon3zoss00wu0705ertl0vd7"       # config.yaml labelbox.dataset_id
OTHER = "cmn5chixy005u07846jctibv1"            # the combined dispatch dataset


def test_the_default_out_is_refused_for_another_dataset(fetch_dataset):
    with pytest.raises(SystemExit) as stop:
        fetch_dataset.main(["--dataset-id", OTHER])
    said = str(stop.value)
    assert fetch_dataset.OUT_PATH in said
    # Both ids, or the reader cannot tell which of the two the file holds.
    assert CONFIGURED in said and OTHER in said
    assert "--out" in said


def test_the_configured_dataset_may_still_use_the_default_out(fetch_dataset):
    """The guard is about the pairing, not about naming the id at all. Passing
    the configured id explicitly is the same run as passing nothing."""
    args = fetch_dataset.parse_args(["--dataset-id", CONFIGURED])
    assert args.out == fetch_dataset.OUT_PATH


def test_the_configured_id_is_the_one_the_guard_compares_against(settings):
    """This file hard-codes the id so the test needs no network. If config
    moves, the hard-coded value is stale and the guard is being tested against
    a dataset nothing reads."""
    assert settings.load_config()["labelbox"]["dataset_id"] == CONFIGURED


class ExportTask:
    def __init__(self, records, *, errors=False, stream_failure=False):
        self.records = records
        self.errors = errors
        self.stream_failure = stream_failure

    def wait_till_done(self):
        pass

    def has_errors(self):
        return self.errors

    def get_buffered_stream(self):
        from types import SimpleNamespace
        for record in self.records:
            yield SimpleNamespace(json=record)
        if self.stream_failure:
            raise RuntimeError("stream interrupted")


def export_client(task):
    from types import SimpleNamespace
    project = SimpleNamespace(name="fixture", uid="fixture-project", data_row_count=1,
                              export=lambda **kwargs: task)
    return SimpleNamespace(get_project=lambda uid: project)


def export_row():
    return {"data_row": {"id": "row1", "global_key": "frame.JPG"},
            "projects": {"fixture-project": {"labels": []}}}


@pytest.mark.parametrize("failure", ["task", "empty", "stream", "identity"])
def test_failed_exports_leave_the_previous_complete_file_untouched(fetch_dataset, tmp_path, failure):
    target = tmp_path / "export_fixture-project.ndjson"
    target.write_text("last complete export\n")
    task = ExportTask([export_row()])
    if failure == "task":
        task.errors = True
    elif failure == "empty":
        task.records = []
    elif failure == "stream":
        task.stream_failure = True
    else:
        task.records = [{"data_row": {"global_key": "frame.JPG"}, "projects": {}}]
    with pytest.raises((RuntimeError, ValueError)):
        fetch_dataset.export_project(export_client(task), "fixture-project", str(tmp_path))
    assert target.read_text() == "last complete export\n"
    assert sorted(p.name for p in tmp_path.iterdir()) == [target.name]


def test_only_a_complete_export_replaces_the_previous_file(fetch_dataset, tmp_path):
    import json
    target = tmp_path / "export_fixture-project.ndjson"
    target.write_text("last complete export\n")
    result = fetch_dataset.export_project(export_client(ExportTask([export_row()])),
                                          "fixture-project", str(tmp_path))
    assert result == str(target)
    assert [json.loads(line) for line in target.read_text().splitlines()] == [export_row()]
