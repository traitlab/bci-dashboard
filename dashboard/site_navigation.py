"""Small, self-contained navigation shared by the published dashboards."""

from html import escape

LINKS = (
    ("index.html", "Home"),
    ("explorer.html", "Browse photos"),
    ("embedding-atlas.html#view=locations", "Drone map"),
    ("embedding-atlas.html", "Similar photos"),
    ("model_health_dashboard.html", "Model health"),
    ("label_queue_dashboard.html", "Labelling queue"),
)

CSS = """
:root{--ink:#213e33;--navy:#245743;--green:#245743;--slate:#52665e;--line:#d3dfd8;--paper:#fff;--pale:#eaf1ec;--surface:#f3f6f3;--focus:#287752;--radius:6px;font:15px/1.5 "Avenir Next",Avenir,system-ui,sans-serif;color:var(--ink);background:var(--surface)}
body{font-family:inherit;color:var(--ink);background:var(--surface);margin:0;max-width:none;padding:0;line-height:1.5}
.site-shell{background:var(--paper);border-top:4px solid var(--green);border-bottom:1px solid var(--line);padding:18px max(24px,calc((100% - 1552px)/2)) 0}
.site-brand{display:inline-flex;align-items:baseline;gap:14px;color:var(--ink);text-decoration:none;font-size:20px;font-weight:700;letter-spacing:-.4px;min-height:38px}
.site-brand span{color:var(--slate);font-size:12px;font-weight:400;letter-spacing:0}
.site-nav{display:flex;flex-wrap:wrap;align-items:center;gap:0 8px;margin:8px 0 0;padding:0;font-size:14px;line-height:1.5}
.site-nav a{display:inline-flex;align-items:center;min-height:48px;padding:10px 12px;color:var(--slate);text-decoration:none;border-radius:4px 4px 0 0;border-bottom:3px solid transparent;white-space:nowrap}
.site-nav a:hover{background:var(--pale);color:var(--green)}
.site-nav a[aria-current=page]{background:var(--pale);border-bottom-color:var(--green);color:var(--green);font-weight:650}
.site-skip{position:absolute;top:8px;left:8px;z-index:30;transform:translateY(-180%);background:white;color:var(--green);padding:10px 14px}
.site-skip:focus{transform:none}
a{color:var(--green);text-underline-offset:3px}
:focus-visible{outline:3px solid var(--focus);outline-offset:3px}
main{min-width:0}
body>header{max-width:1600px;margin:auto;background:transparent;color:var(--ink);border:0;padding:24px 24px 0}
body>header h1{font-size:26px;line-height:1.25;font-weight:650;letter-spacing:-.6px;color:var(--ink);margin:0}
body>header p{font-size:14px;color:var(--slate);margin:6px 0 0}
button,input,select,textarea{font-family:inherit;border-color:#a8bdb0;border-radius:var(--radius);accent-color:var(--green)}
button,select,input[type=search]{min-height:44px}
button:hover{background:var(--pale)}
button:disabled{cursor:default}
button[aria-pressed=true]{border-color:var(--green)}
body[data-workspace=reports] main{max-width:1168px;margin:auto;padding:28px 24px 64px}
body[data-workspace=reports] h1{font-size:26px;font-weight:650;color:var(--ink);letter-spacing:-.6px}
body[data-workspace=reports] summary{color:var(--green)}
body[data-workspace=reports] h2{color:var(--ink)}
body[data-workspace=reports] th{background:var(--pale);color:var(--ink)}
body[data-workspace=reports] .hero .metric.first{background:var(--pale);border-color:#9ebca8}
body[data-workspace=reports] .hero .metric .e,body[data-workspace=reports] .hero .metric .src{color:var(--green)}
body[data-workspace=reports] .hero .metric .e{text-transform:none;letter-spacing:0;font-size:.78rem}
body[data-workspace=reports] details.panel>summary{color:var(--green)}
body[data-workspace=reports] .hero .metric,body[data-workspace=reports] details.panel{box-shadow:none;border-color:var(--line);border-radius:var(--radius)}
@media(max-width:640px){.site-shell{padding:12px 12px 0}.site-brand{display:flex;flex-wrap:wrap;gap:0 12px;font-size:18px}.site-brand span{font-size:11px}.site-nav{gap:0 2px}.site-nav a{font-size:12px;padding:8px;min-height:44px}body>header{padding:20px 14px 0}body>header h1{font-size:23px}body[data-workspace=reports] main{padding:22px 14px 40px}}
@media(prefers-reduced-motion:reduce){html{scroll-behavior:auto}}
@media print{body{background:#fff;color:#000}.site-shell,.site-skip{display:none}
body[data-workspace=reports] main{padding:0;max-width:none}}
"""


def navigation(current, *, available=None):
    """Keep the same task labels and expose the current page to assistive tools."""
    photo_pages = ('' if available is None else ' data-photo-pages="'
                   + ' '.join(page for page in ('embedding-atlas.html', 'crownfirst-atlas.html')
                              if page in available) + '"')
    links = []
    for destination, label in LINKS:
        page, _, fragment = destination.partition("#")
        if available is not None and page not in available:
            continue
        view = fragment.removeprefix("view=") if fragment else "photos"
        active = current == destination
        attributes = ' aria-current="page"' if active else ""
        if page in ("embedding-atlas.html", "crownfirst-atlas.html"):
            task_id = {"photos": "similarPhotosTask", "locations": "cameraMapTask", "models": "compareModelsTask"}[view]
            attributes += f' data-atlas-view="{view}" data-site-task="{view}" id="{task_id}"'
        links.append(f'<a href="{destination}"{attributes}>{escape(label)}</a>')
    return ('<a class="site-skip" onclick="event.preventDefault();'
            'document.getElementById(\'main-content\').focus()" '
            'href="#main-content">Skip to content</a>'
            '<div class="site-shell" role="region" aria-label="Site"><a class="site-brand" href="index.html">'
            'Panama canopy<span>Photo and labelling workspace</span></a>'
            '<nav class="site-nav" aria-label="Dashboard pages"' + photo_pages + '>'
            + "".join(links) + '</nav></div>')
