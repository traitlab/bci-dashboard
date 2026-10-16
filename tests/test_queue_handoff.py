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
    assert "15 of its 95 photos" in html
    assert "15 of its 100 photos" not in html


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


def test_shared_status_reasons_preserve_biodiversity_review(status_words):
    assert "manual identification" in status_words.STATUS_REASON["hard"].lower()
    assert "Manual identification and biodiversity labels remain useful" in status_words.STATUS_REASON["out_of_scope"]
    assert "biodiversity importance" in status_words.STATUS_REASON["reliable"]
    assert "more labels will not fix" not in " ".join(status_words.STATUS_REASON.values()).lower()
