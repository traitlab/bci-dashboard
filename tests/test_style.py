"""The one coupling the assets/style split has to keep honest.

``style.py`` holds the stylesheet; ``assets.py`` and the panel modules write the
markup it styles. ADR 0001 declined that split on the grounds that the coupling
between a class a renderer writes and the rule that styles it would become "a
convention nobody can check". ADR 0003 made the split anyway, on the condition
that this file checks it. So these two tests are the terms of that decision, not
housekeeping: a class written with no rule, or a rule matching nothing, fails
here rather than shipping as an unstyled element or dead bytes in every page.

    .venv/bin/pytest tests/test_style.py
"""

from __future__ import annotations

import ast
import io
import os
import re
import tokenize

DASHBOARD = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dashboard")

# Class names in the stylesheet, read from the selectors only: the declaration
# blocks are stripped first so a colour like `#panel` or a font name cannot be
# mistaken for one.
_CLASS_RE = re.compile(r"\.([a-zA-Z][\w-]*)")

# `class="a b"` written out in full. Composed ones (`class="tag {st}"`) are not
# matched, on purpose: their pieces are status keys, covered by test_page.py.
_EMITTED_RE = re.compile(r'class="([a-zA-Z][\w \-]*)"')


def _css_classes(style):
    return set(_CLASS_RE.findall(re.sub(r"\{[^}]*\}", "", style.CSS)))


def _sources():
    return {f: open(os.path.join(DASHBOARD, f), encoding="utf-8").read()
            for f in sorted(os.listdir(DASHBOARD)) if f.endswith(".py")}


def _without_prose(src):
    """``src`` with every comment and docstring blanked out.

    A class name that survives this is one the code writes, not one a sentence
    happens to mention. The dead-rule check below reads only this: a rule kept
    alive by English in a docstring is a rule nothing wears.
    """
    drop = set()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef)) and ast.get_docstring(node) is not None:
            doc = node.body[0]
            drop.update(range(doc.lineno, doc.end_lineno + 1))
    for tok in tokenize.generate_tokens(io.StringIO(src).readline):
        if tok.type == tokenize.COMMENT:
            drop.add(tok.start[0])
    return "\n".join("" if i in drop else line
                      for i, line in enumerate(src.splitlines(), 1))


def test_every_class_a_builder_writes_has_a_rule_in_the_stylesheet(style):
    """An unstyled element is invisible in a diff and obvious on the page."""
    css = _css_classes(style)
    missing = {}
    for name, src in _sources().items():
        if name == "style.py":
            continue
        for m in _EMITTED_RE.finditer(src):
            for cls in m.group(1).split():
                if cls not in css:
                    missing.setdefault(cls, name)
    assert not missing, f"classes written with no rule to style them: {missing}"


def test_every_rule_in_the_stylesheet_matches_something(style):
    """A rule nothing wears is bytes in every page and a lie about the markup.

    The stylesheet is a strict subset of labelfirst's, kept that way by hand
    (see style.py's docstring), so a rule that stops matching is the expected
    kind of drift, not an unlikely one. Classes the script adds at runtime
    (`asc`, `desc`, `hidden`, `sortable`) count: they appear in style.py's own
    JS, which is one of the sources read here.

    Comments and docstrings are stripped first, and a trailing `{` counts as a
    boundary. Without the strip, `.hero .metric` passed on the word "metric"
    inside an English sentence while the line that emits it,
    `f'<div class="metric{...}">'`, was invisible to the search: the rule was
    live, the guard was reading prose, and condensing that sentence would have
    reported a live rule dead.
    """
    src = "".join(_without_prose(s) for s in _sources().values())
    dead = [c for c in sorted(_css_classes(style))
            if not re.search(r"[\"'\s>]" + re.escape(c) + r"[\"'\s<{]", src)]
    assert not dead, f"stylesheet rules matching no markup and no script: {dead}"
