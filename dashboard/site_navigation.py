"""Small, self-contained navigation shared by the published dashboards."""

from html import escape

LINKS = (
    ("index.html", "Home"),
    ("explorer.html", "Browse photos"),
    ("embedding-atlas.html", "Similar photos"),
    ("model_health_dashboard.html", "Model health"),
    ("label_queue_dashboard.html", "Labelling queue"),
)

CSS = """
.site-nav{display:flex;flex-wrap:wrap;align-items:center;gap:4px 10px;padding:10px 0;margin:0 0 18px;border-bottom:1px solid #c6d6cf;font:13px/1.4 system-ui,sans-serif}
.site-nav a{display:inline-flex;align-items:center;min-height:44px;padding:8px 10px;color:#245743;text-decoration:none;border-radius:4px}
.site-nav a:hover{background:#edf2ef;text-decoration:underline}
.site-nav a[aria-current=page]{background:#e0ebe3;color:#16432e;font-weight:650}
.site-nav a:focus-visible,.site-skip:focus-visible{outline:3px solid #2d8061;outline-offset:3px}
.site-skip{position:absolute;top:8px;left:8px;z-index:20;transform:translateY(-160%);background:white;color:#16432e;padding:10px 14px}
.site-skip:focus{transform:none}
@media(max-width:640px){.site-nav{gap:0 3px;margin-bottom:12px}.site-nav a{font-size:12px;padding:8px}}
@media print{.site-nav,.site-skip{display:none}}
"""


def navigation(current, *, available=None):
    """Keep the same task labels and expose the current page to assistive tools."""
    links = []
    for destination, label in LINKS:
        if available is not None and destination not in available:
            continue
        active = current == destination or (
            destination == "embedding-atlas.html" and current == "crownfirst-atlas.html"
        )
        attributes = ' aria-current="page"' if active else ""
        if destination == "embedding-atlas.html":
            attributes += ' data-atlas-view="photos" data-site-task="similar" id="similarPhotosTask"'
        links.append(f'<a href="{destination}"{attributes}>{escape(label)}</a>')
    return ('<a class="site-skip" onclick="event.preventDefault();'
            'document.getElementById(\'main-content\').focus()" '
            'href="#main-content">Skip to content</a>'
            '<nav class="site-nav" aria-label="Dashboard pages">'
            + "".join(links) + '</nav>')
