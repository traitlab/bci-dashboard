"""Rebuild published interfaces from their embedded, recorded data, offline."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from assets import css_for, strip_comments
from build_index import build as build_index
from embedding_atlas_assets import HTML as ATLAS_HTML
from explorer_assets import HTML as EXPLORER_HTML
from site_navigation import CSS as SITE_CSS
from site_navigation import navigation
from style import CSS as REPORT_CSS

PHOTO_PAGES = {
    "explorer.html": ("explorer-data", EXPLORER_HTML, "__EXPLORER_DATA__"),
    "embedding-atlas.html": ("atlas-data", ATLAS_HTML, "__ATLAS_DATA__"),
    "crownfirst-atlas.html": ("atlas-data", ATLAS_HTML, "__ATLAS_DATA__"),
}
REPORT_PAGES = ("model_health_dashboard.html", "label_queue_dashboard.html")


def refresh_page(name: str, original: str, available: set[str]) -> str:
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
        return (template.replace("__SITE_CSS__", SITE_CSS)
                .replace("__SITE_NAV__", navigation(name, available=available))
                .replace(placeholder, payload.group(1)))
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
    return updated


def refresh_site(source: Path, output: Path) -> None:
    """Validate every page before writing, including when updating in place."""
    missing = [name for name in REPORT_PAGES if not (source / name).is_file()]
    if missing:
        raise ValueError("Missing recorded reports: " + ", ".join(missing))
    names = [*REPORT_PAGES, *(name for name in PHOTO_PAGES if (source / name).is_file())]
    available = set(names) | {"index.html"}
    pages = {name: refresh_page(name, (source / name).read_text(encoding="utf-8"), available)
             for name in names}
    # Home derives each date from its own page rather than a fresh UI build date.
    with tempfile.TemporaryDirectory(prefix="bci-site-ui-") as folder:
        stage = Path(folder)
        for name, text in pages.items():
            (stage / name).write_text(text, encoding="utf-8")
        pages["index.html"] = build_index(folder)
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
    except (OSError, ValueError) as error:
        parser.exit(1, f"UI refresh failed: {error}\n")


if __name__ == "__main__":
    main()
