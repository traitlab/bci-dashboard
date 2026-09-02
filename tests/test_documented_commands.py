"""Every command the docs print, checked against the script it names.

Twice this month a documented command could not have run. `rank_unsent.py`
printed a backtest whose `--species-col` default named a column the labels
file does not have, and it had been that way long enough for the default to
look deliberate. Nobody noticed, because a command in a docstring is read far
more often than it is typed.

So the commands are collected from the README, the shell scripts in `bin/`,
the ADRs and every module docstring, and each one is put to the script it
names: the file has to exist, and every flag has to be one that script's
parser accepts. Values are not checked. `path/to/export.ndjson` is a
placeholder and should stay one.

Flags are read from the source first, which is fast and covers the scripts
that build their own parser. The four page builders share a parser factory in
`dashboard/page.py`, so a flag that is not in the source is put to the script
itself with `--help`, which is the parser rather than a guess at it.

    .venv/bin/pytest tests/test_documented_commands.py
"""

from __future__ import annotations

import ast
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
CODE_DIRS = ("dashboard", "predict", "labelling")

# `python3 dashboard/measure.py --out-dir X`, and the same line written with
# the venv's interpreter. Stops at a pipe, a comment or the end of the line.
COMMAND = re.compile(
    r"(?:python3?|[\w./]*bin/python3?)\s+"
    r"((?:" + "|".join(CODE_DIRS) + r")/[\w/]+\.py)"
    r"([^\n|&;#]*)")
FLAG = re.compile(r"(--[a-z][\w-]*)")
DECLARED = re.compile(r"add_argument\(\s*\"(--[\w-]+)\"")


def documented() -> dict[tuple[str, frozenset], list[str]]:
    """Every command in the prose, with where it was printed."""
    sources = {}
    for path in [REPO / "README.md", *(REPO / "bin").glob("*"),
                 *(REPO / "docs").rglob("*.md")]:
        sources[path.name] = path.read_text(encoding="utf-8")
    for directory in CODE_DIRS:
        for path in sorted((REPO / directory).glob("*.py")):
            doc = ast.get_docstring(ast.parse(path.read_text(encoding="utf-8")))
            if doc:
                sources[f"{directory}/{path.name} docstring"] = doc

    found: dict[tuple[str, frozenset], list[str]] = {}
    for where, text in sources.items():
        for script, rest in COMMAND.findall(text):
            key = (script, frozenset(FLAG.findall(rest)))
            found.setdefault(key, []).append(where)
    return found


def accepts(script: str, flag: str) -> bool:
    """Whether `script` takes `flag`, asking the parser when the source is
    quiet: the page builders take theirs from `dashboard/page.py`."""
    if flag in DECLARED.findall((REPO / script).read_text(encoding="utf-8")):
        return True
    helped = subprocess.run([sys.executable, str(REPO / script), "--help"],
                            capture_output=True, text=True, cwd=REPO, check=False)
    return flag in helped.stdout


COMMANDS = sorted(documented().items())


def test_the_docs_print_commands_at_all():
    """A regex that quietly matches nothing would pass every test below."""
    assert len(COMMANDS) > 20, f"only {len(COMMANDS)} commands found; the regex broke"


@pytest.mark.parametrize("script,flags,where", [
    (script, sorted(flags), ", ".join(sorted(set(where))))
    for (script, flags), where in COMMANDS])
def test_a_documented_command_names_a_script_that_takes_those_flags(
        script, flags, where):
    assert (REPO / script).exists(), f"{where} runs {script}, which does not exist"
    unknown = [flag for flag in flags if not accepts(script, flag)]
    assert not unknown, (
        f"{where} runs `{script} {' '.join(flags)}` and it does not take "
        f"{unknown}. Either the flag was renamed or the command was never run.")
