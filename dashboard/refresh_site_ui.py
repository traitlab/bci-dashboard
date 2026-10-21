"""Rebuild published interfaces from their embedded, recorded data, offline."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from assets import css_for, strip_comments
from atlas_inventory import join_photo_inventory
from build_index import build as build_index, build_about
from embedding_atlas_assets import HTML as ATLAS_HTML
from explorer_assets import HTML as EXPLORER_HTML
from site_navigation import CSS as SITE_CSS, FAVICON
from site_navigation import navigation
from style import CSS as REPORT_CSS

PHOTO_PAGES = {
    "explorer.html": ("explorer-data", EXPLORER_HTML, "__EXPLORER_DATA__"),
    "embedding-atlas.html": ("atlas-data", ATLAS_HTML, "__ATLAS_DATA__"),
    "crownfirst-atlas.html": ("atlas-data", ATLAS_HTML, "__ATLAS_DATA__"),
}
REPORT_PAGES = ("model_health_dashboard.html", "label_queue_dashboard.html")


def refresh_page(
    name: str, original: str, available: set[str], catalogue: dict | None = None,
    catalogue_source: dict | None = None,
) -> str:
    """Replace presentation while retaining the recorded data and report body."""
    if name in PHOTO_PAGES:
        data_id, template, placeholder = PHOTO_PAGES[name]
        payload = re.search(
            rf'<script id="{data_id}" type="application/json">(.*?)</script>',
            original, re.DOTALL,
        )
        if payload is None:
            raise ValueError(f"{name}: embedded {data_id} is missing")
        data = json.loads(payload.group(1))
        population = "photos" if name == "explorer.html" else "points"
        if not isinstance(data, dict) or not isinstance(data.get(population), list):
            raise ValueError(f"{name}: recorded {population} must be a list")
        recorded_payload = payload.group(1)
        if population == "points" and catalogue is not None:
            data = join_photo_inventory(data, catalogue, catalogue_source or {})
            recorded_payload = json.dumps(data, separators=(",", ":"), allow_nan=False).replace("<", "\\u003c")
        if population == "points" and not data["points"]:
            raise ValueError(f"{name}: atlas requires at least one positioned photo; recorded pages retained")
        return (template.replace("__SITE_CSS__", SITE_CSS)
                .replace("__SITE_NAV__", navigation(name, available=available))
                .replace(placeholder, recorded_payload))
    if name not in REPORT_PAGES:
        raise ValueError(f"Unsupported dashboard page: {name}")
    if '<main id="main-content"' not in original:
        raise ValueError(f"{name}: report content is missing")
    updated, replaced = re.subn(
        r'<body\b[^>]*>.*?(<main\b)',
        lambda match: ('<body data-workspace="reports">'
                       + navigation(name, available=available) + match.group(1)),
        original, count=1, flags=re.DOTALL,
    )
    if replaced != 1:
        raise ValueError(f"{name}: page body is missing")
    css = css_for(strip_comments(REPORT_CSS), updated)
    updated, replaced = re.subn(
        r"<style>.*?</style>", lambda _: f"<style>{css}</style>",
        updated, count=1, flags=re.DOTALL,
    )
    if replaced != 1:
        raise ValueError(f"{name}: report stylesheet is missing")
    if 'rel="icon"' not in updated:
        updated = updated.replace("</title>", "</title>" + FAVICON, 1)
    return tag_queue_figure(updated) if name == "label_queue_dashboard.html" else updated


def tag_queue_figure(text: str) -> str:
    """Mark a recorded queue hero with the figure the index reads, taken from its own Queued card."""
    queued = re.search(r'<div class="e">Queued</div><div class="row"><div class="v">([\d,]+)</div>'
                       r'.*?<div class="l">(unlabelled photos)</div>', text, re.DOTALL)
    if queued is None or 'data-tile="' in text:
        return text
    return re.sub(r'<div class="hero([^"]*)">', rf'<div class="hero\1" data-tile="{queued.group(1)} {queued.group(2)}">',
                  text, count=1)


def refresh_site(source: Path, output: Path) -> None:
    """Validate every page before writing, including when updating in place."""
    missing = [name for name in REPORT_PAGES if not (source / name).is_file()]
    if missing:
        raise ValueError("Missing recorded reports: " + ", ".join(missing))
    names = [*REPORT_PAGES, *(name for name in PHOTO_PAGES if (source / name).is_file())]
    available = set(names) | {"index.html", "about.html"}
    catalogue = None
    catalogue_source = None
    if "explorer.html" in names:
        text = (source / "explorer.html").read_text(encoding="utf-8")
        match = re.search(r'<script id="explorer-data" type="application/json">(.*?)</script>', text, re.DOTALL)
        if match is None:
            raise ValueError("explorer.html: embedded explorer-data is missing")
        catalogue = json.loads(match.group(1))
        catalogue_source = {"file": "explorer.html#explorer-data", "sha256": hashlib.sha256(match.group(1).encode()).hexdigest()}
    pages = {name: refresh_page(name, (source / name).read_text(encoding="utf-8"), available,
                                catalogue, catalogue_source) for name in names}
    # Home derives each date from its own page rather than a fresh UI build date.
    with tempfile.TemporaryDirectory(prefix="bci-site-ui-") as folder:
        stage = Path(folder)
        for name, text in pages.items():
            (stage / name).write_text(text, encoding="utf-8")
        pages["index.html"] = build_index(folder)
    pages["about.html"] = build_about(available)
    output.mkdir(parents=True, exist_ok=True)
    for name, text in pages.items():
        (output / name).write_text(text, encoding="utf-8")
    if source.resolve() != output.resolve():
        for csv in source.glob("*.csv"):
            shutil.copy2(csv, output / csv.name)
    print(f"Refreshed recorded dashboard interfaces in {output}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site", type=Path, default=Path("docs"))
    parser.add_argument("--out", type=Path, default=Path("build/ui-preview"))
    args = parser.parse_args()
    try:
        refresh_site(args.site, args.out)
    except (OSError, TypeError, ValueError) as error:
        parser.exit(1, f"UI refresh failed: {error}\n")


if __name__ == "__main__":
    main()
