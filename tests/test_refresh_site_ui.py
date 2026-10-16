"""A UI-only rebuild preserves recorded populations, figures and dates."""

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def recorded_site(folder):
    folder.mkdir()
    report = ('<!doctype html><html><head><style>body{color:red}</style></head><body>'
              '<nav>Old navigation</nav><main id="main-content" tabindex="-1">'
              '<h1>Recorded report</h1><div class="subtitle">labels as of 2026-08-27</div>'
              '<p>17 of 33 reviewed frames</p><a href="evidence.csv">Evidence</a>'
              '</main><script>window.recorded=true</script></body></html>')
    for name in ("model_health_dashboard.html", "label_queue_dashboard.html"):
        (folder / name).write_text(report)
    payload = json.dumps({"schema_version": 1, "photos": [], "taxa": [],
                          "provenance": {"source": "recorded"}})
    (folder / "explorer.html").write_text(
        '<script id="explorer-data" type="application/json">' + payload + '</script>')
    (folder / "evidence.csv").write_text("matched,total\n17,33\n")
    return report, payload


def refresh(source, output):
    return subprocess.run(
        [sys.executable, "-S", str(ROOT / "dashboard/refresh_site_ui.py"),
         "--site", str(source), "--out", str(output)],
        capture_output=True, text=True, check=False,
    )


def test_offline_ui_refresh_preserves_evidence_and_optional_page_boundaries(tmp_path):
    source, output = tmp_path / "recorded", tmp_path / "preview"
    report, payload = recorded_site(source)
    result = refresh(source, output)
    assert result.returncode == 0, result.stderr
    updated = (output / "model_health_dashboard.html").read_text()
    for tag in ("main", "script"):
        pattern = rf"<{tag}\b.*?</{tag}>"
        assert re.search(pattern, updated, re.DOTALL).group() == re.search(pattern, report, re.DOTALL).group()
    assert 'data-workspace="reports"' in updated
    assert 'class="site-brand"' in updated
    assert "Old navigation" not in updated
    explorer = (output / "explorer.html").read_text()
    assert f'<script id="explorer-data" type="application/json">{payload}</script>' in explorer
    home = (output / "index.html").read_text()
    assert "labels as of 2026-08-27" in home
    assert 'href="explorer.html"' in home
    assert 'href="crownfirst-atlas.html' not in home
    assert (output / "evidence.csv").read_bytes() == (source / "evidence.csv").read_bytes()
    assert (source / "model_health_dashboard.html").read_text() == report
    # Updating already refreshed pages does not duplicate the masthead.
    again = refresh(output, output)
    assert again.returncode == 0, again.stderr
    assert (output / "model_health_dashboard.html").read_text().count('class="site-brand"') == 1


def test_invalid_payload_stops_before_any_output_is_overwritten(tmp_path):
    source, output = tmp_path / "recorded", tmp_path / "preview"
    recorded_site(source)
    output.mkdir()
    (output / "index.html").write_text("Previous good home")
    (source / "explorer.html").write_text("No recorded population")
    result = refresh(source, output)
    assert result.returncode != 0
    assert "embedded explorer-data is missing" in result.stderr
    assert (output / "index.html").read_text() == "Previous good home"
    assert not (output / "model_health_dashboard.html").exists()
