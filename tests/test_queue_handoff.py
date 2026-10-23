"""Queue handoffs preserve the producer's photo keys and live-action boundary."""
from types import SimpleNamespace


def test_queue_coverage_uses_full_photo_keys(queue_panels, monkeypatch):
    rows = [("long_tail", "DJI_a.JPG", "species a", 0.1, 1, "0.500")]
    url = "https://app.labelbox.com/projects/projectA/data-rows/rowA"
    monkeypatch.setattr(queue_panels.hc, "inventory_image_urls",
                        lambda: {"comb_DJI_a.JPG": "https://example.com/a.jpg"})
    monkeypatch.setattr(queue_panels.hc, "labelbox_urls",
                        lambda: {"comb_DJI_a.JPG": url})
    html = queue_panels.links_note(SimpleNamespace(queue_rows=rows))
    assert "1 of 1 rows" in html
    assert "filled on 1." in html
    assert "No frame links" not in html


def test_queue_preview_opens_exact_photo_and_recorded_annotation(queue_panels, monkeypatch):
    url = "https://app.labelbox.com/projects/projectA/data-rows/rowA"
    monkeypatch.setattr(queue_panels.hc, "labelbox_urls",
                        lambda: {"comb_DJI_a.JPG": url})
    c = SimpleNamespace(
        queue_rows=[("long_tail", "DJI_a.JPG", "species a", 0.1, 1, "0.500"),
                    ("long_tail", "DJI_b.JPG", "species b", 0.2, 2, "0.400")],
        support={}, selection_audit=None, n_batch1=2,
        available_pages={"explorer.html"})
    html = queue_panels.send_preview_table(c)
    assert 'href="explorer.html#frame=comb_DJI_a.JPG"' in html
    assert 'href="explorer.html#frame=comb_DJI_b.JPG"' in html
    assert f'href="{url}"' in html
    assert html.count('href="https://app.labelbox.com/') == 1
    assert "No Labelbox item link recorded" in html
    assert html.index("DJI_a.JPG") < html.index("DJI_b.JPG")
    assert "0.500" in html and "0.400" in html


def test_queue_preview_without_explorer_keeps_exact_available_links(queue_panels, monkeypatch):
    image = "https://example.com/a.jpg?token=recorded&size=full"
    annotation = "https://app.labelbox.com/projects/projectA/data-rows/rowB"
    monkeypatch.setattr(queue_panels.hc, "inventory_image_urls",
                        lambda: {"comb_DJI_a.JPG": image})
    monkeypatch.setattr(queue_panels.hc, "labelbox_urls",
                        lambda: {"comb_DJI_b.JPG": annotation})
    c = SimpleNamespace(
        queue_rows=[("long_tail", "DJI_a.JPG", "species a", 0.1, 1, "0.500"),
                    ("long_tail", "DJI_b.JPG", "species b", 0.2, 2, "0.400")],
        support={}, selection_audit=None, n_batch1=2)
    html = queue_panels.send_preview_table(c)
    assert "explorer.html" not in html
    assert 'href="https://example.com/a.jpg?token=recorded&amp;size=full"' in html
    assert '<td><code class="key">DJI_b.JPG</code>' in html
    assert f'href="{annotation}"' in html
    assert html.count("No Labelbox item link recorded") == 1


def test_batch_comparison_uses_actual_packed_size(queue_panels):
    c = SimpleNamespace(selection_audit=None, n_batch1=95, queue_rows=[None] * 100)
    html = queue_panels.ungraded_note(c)
    assert "15 of the 95 photos in batch 1" in html
    assert "15 of the 100 photos in batch 1" not in html


def test_dispatch_description_calls_test_a_live_action(queue_panels):
    html = queue_panels.DISPATCH
    assert "live five-photo batch" in html
    assert "updates metadata" in html
    assert "offline preview" in html
    assert "dry run" not in html


def test_queue_notes_do_not_treat_guesses_or_empty_answers_as_labels(queue_panels, monkeypatch):
    monkeypatch.setattr(queue_panels.hc, "labelbox_urls", dict)
    c = SimpleNamespace(queue_rows=[], support={}, selection_audit=None,
                        n_batch1=0, n_no_answer=2, queue_cams={"tele": 0})
    preview = queue_panels.send_preview_table(c)
    assert "Confidence breaks ranking ties" in preview
    assert "score does not confirm a label" in preview
    assert "not a reason to doubt the name" not in preview
    notes = queue_panels.send_notes(c)
    assert "empty answer does not establish that no plant is visible" in notes
    assert "Likeliest to be junk" not in notes


def test_species_statuses_are_review_guidance_not_biodiversity_skip_rules(queue_panels):
    c = SimpleNamespace(counts={key: 1 for key in queue_panels.STATUS},
                        n_sp=len(queue_panels.STATUS), gen_one=3, n_cand=5)
    html = queue_panels.p_todo(c)
    assert '<details class="panel" id="cheapest-confirmation-work">' in html
    assert "How to review model guesses" in html
    assert "not biodiversity value" in html
    assert "manual identification" in html.lower()
    assert "lower priority for checking model guesses" in html.lower()
    assert "need a yes or no" not in html
    assert "can skip" not in html and "Skip." not in html
    assert "More labels will not fix" not in html
    assert "alternatives outside the returned list" in html
    for key in queue_panels.STATUS:
        assert f'class="tag {key}"' in html


CALIBRATION = (
    "row_type,scope,band,n_crowns,top1_accuracy,fraction_of_scope,n_correct,n_wrong,"
    "error_rate_if_auto_accepted\n"
    "bin,all_species_level_gt,\"[0.0,0.5)\",842,0.3777,0.2569,318,524,\n"
    "bin,all_species_level_gt,\"[0.5,0.8)\",672,0.8554,0.2051,574,98,\n"
    "bin,all_species_level_gt,\"[0.8,1.0)\",1763,0.9711,0.5380,1712,51,\n"
    "threshold,all_species_level_gt,>=0.8,1763,0.9711,0.5380,1712,51,0.0289\n"
    "threshold,species_with_n_ge_10,>=0.8,1681,0.9750,0.5803,1639,42,0.0250\n")


def test_threshold_evidence_prints_the_calibration_table_values(queue_panels, tmp_path):
    (tmp_path / "confidence_calibration.csv").write_text(CALIBRATION, encoding="utf-8")
    html = queue_panels.threshold_evidence(SimpleNamespace(verify_dir=str(tmp_path)))
    assert "right on 1,712 of 1,763 frames (97.1%)" in html
    assert "right on 318 of 842 frames (37.8%)" in html
    assert "On the 3,277 labelled frames" in html
    assert "A confident guess can still be wrong: 51 frames" in html
    assert "0.80 is the confidence line; 0.50 marks low confidence." in html
    assert "Both values were set by judgement, not fitted to this table" in html
    assert "cut-off" not in html
    # One open line names the lines; the numbers sit in a closed block under it.
    line, closed = html.split('<details class="more">', 1)
    assert line == '<p class="note">Confidence lines: 0.80 for the wait rule, 0.50 for low confidence.</p>'
    assert "1,712 of 1,763" in closed and "set by judgement" in closed


def test_threshold_evidence_is_empty_without_its_rows(queue_panels, tmp_path):
    assert queue_panels.threshold_evidence(SimpleNamespace(verify_dir=str(tmp_path))) == ""
    assert queue_panels.threshold_evidence(SimpleNamespace()) == ""
    (tmp_path / "confidence_calibration.csv").write_text(
        CALIBRATION.replace("[0.0,0.5)", "[0.0,0.4)"), encoding="utf-8")
    assert queue_panels.threshold_evidence(SimpleNamespace(verify_dir=str(tmp_path))) == ""
    (tmp_path / "confidence_calibration.csv").write_text(
        CALIBRATION.replace("842,0.3777,0.2569,318,524", "0,,0.0,0,0"), encoding="utf-8")
    assert queue_panels.threshold_evidence(SimpleNamespace(verify_dir=str(tmp_path))) == ""


def test_shared_status_reasons_preserve_biodiversity_review(status_words):
    assert "manual identification" in status_words.STATUS_REASON["hard"].lower()
    assert "Manual identification and biodiversity labels remain useful" in status_words.STATUS_REASON["out_of_scope"]
    assert "biodiversity importance" in status_words.STATUS_REASON["reliable"]
    assert "more labels will not fix" not in " ".join(status_words.STATUS_REASON.values()).lower()


READOUT_HEAD = ("scope,status,arm,n_sent,n_labelled,n_with_guess,corrections,corrections_lo,corrections_hi,"
                "new_rows,long_tail_rows\n")


def _readout(queue_panels, tmp_path, body=None):
    if body is not None:
        (tmp_path / "round_readout.csv").write_text(READOUT_HEAD + body, encoding="utf-8")
    return SimpleNamespace(verify_dir=str(tmp_path), selection_audit=None, n_batch1=95,
                           queue_rows=[None] * 100)


def test_readout_is_pending_without_a_closed_round(queue_panels, tmp_path):
    c = _readout(queue_panels, tmp_path)
    assert "pending, no round closed yet" in queue_panels.readout_block(c)
    c = _readout(queue_panels, tmp_path, "all,pending,prioritised,100,0,0,,,,0,0\n")
    assert "pending, no round closed yet" in queue_panels.readout_block(c)
    assert "has not been measured yet" in queue_panels.ungraded_note(c)
    assert "15 of the 95 photos in batch 1" in queue_panels.ungraded_note(c)


def test_readout_prints_counts_with_the_rate_once_closed(queue_panels, tmp_path):
    c = _readout(queue_panels, tmp_path,
                 "all,closed,prioritised,100,80,80,20,0.16,0.36,12,30\n"
                 "all,closed,control,15,10,10,1,0.01,0.40,2,3\n"
                 "all,closed,extra,5,4,0,0,,,0,0\n")
    html = queue_panels.readout_block(c)
    assert "pending" not in html
    assert ">80<" in html and ">20<" in html and ">10<" in html
    assert "25.0% (16.0% to 36.0%)" in html
    assert ">n/a<" in html
    assert ">random control<" in html and ">arm<" not in html
    note = queue_panels.ungraded_note(c)
    assert "has not been measured yet" not in note
    assert "Prioritised vs random control." in note


def test_readout_refuses_an_interval_that_is_not_a_rate(queue_panels, tmp_path):
    import pytest
    c = _readout(queue_panels, tmp_path, "all,closed,prioritised,100,80,80,20,12,30,0,0\n")
    with pytest.raises(SystemExit, match="VERIFY FAIL"):
        queue_panels.readout_block(c)
