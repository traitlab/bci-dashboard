"""The GBIF backbone key behind a Labelbox option label, read offline.

Every option in the Labelbox ``Taxón`` question carries a display label and a
``value`` that is a GBIF backbone key: ``Abuta panamensis-ABUTPA-ABUP`` is
3830289. Every species on a Pl@ntNet checklist carries ``gbifId`` from the same
backbone. Joining the two by name answers "is this species on the list" wrongly
every time the botanists rename an option, and they do: ``Pochota quinata``
became ``Pochota fendleri`` and ``Quararibea asterolepis`` became ``Quararibea
stenophylla``, all of them on the list under the new name and read as absent
under the old one.

``labelling/build_gbif_keys.py`` writes ``data/gbif_keys.json`` from the live
ontology. This module reads it back. It makes no network call: a missing file
is the normal state of a fresh clone and every caller degrades to the name
join rather than aborting, which is what keeps the page build offline.

``accepted`` is not optional dressing. GBIF holds one taxon under a synonym key
and an accepted key, and the label and the checklist do not always pick the
same one. Four species read as absent until both ends were put through it.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass

from core import BASE, normalize

KEYS_JSON = os.path.join(BASE, "gbif_keys.json")

_CODE = re.compile(r"^[A-Z0-9]{2,}$")


def split_codes(label: str) -> tuple[str, list[str]]:
    """``Abuta panamensis-ABUTPA-ABUP`` -> ``("Abuta panamensis", [ABUTPA, ABUP])``.

    Trailing ALL-CAPS/digit tokens only, popped from the right, so a hyphenated
    epithet (``Macfadyena unguis-cati``) keeps its second half.
    """
    parts = label.split("-")
    codes: list[str] = []
    while len(parts) > 1 and _CODE.match(parts[-1]):
        codes.insert(0, parts.pop())
    return "-".join(parts).strip(), codes


@dataclass(frozen=True)
class KeyIndex:
    ontology_name: str
    fetched: str
    by_code: dict   # collection code -> GBIF key
    by_name: dict   # normalize()'d option label -> GBIF key
    by_legacy: dict # normalize()'d retired label -> GBIF key of the option that replaced it
    accepted: dict  # str(key) -> accepted usage key

    def key_for(self, raw_label: str) -> int | None:
        """The accepted key a botanist's label stands for, or ``None``.

        Code first, when the label still carries one. The ground truth strips
        them, so most labels arrive as a bare name: the current ontology's names
        answer for those, and ``by_legacy`` answers for the ones it has retired,
        which is where ``Pochota quinata`` becomes the key the option now
        labelled ``Pochota fendleri`` holds.
        """
        if not raw_label:
            return None
        name, codes = split_codes(raw_label)
        for code in codes:
            key = self.by_code.get(code)
            if key is not None:
                return self.accepted_key(key)
        nn = normalize(name)
        key = self.by_name.get(nn, self.by_legacy.get(nn))
        return None if key is None else self.accepted_key(key)

    def accepted_key(self, key: int) -> int:
        """``key`` resolved through the backbone, or itself when unresolved."""
        return self.accepted.get(str(key), key)


def load_keys(path: str | None = None) -> KeyIndex | None:
    """Read ``data/gbif_keys.json``, or ``None`` when it is not there.

    ``None`` is not an error: ``labelling/build_gbif_keys.py`` is a separate,
    network-touching step and ``dashboard/`` builds every page offline.
    """
    p = path or KEYS_JSON
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as f:
        doc = json.load(f)
    return KeyIndex(
        ontology_name=doc.get("ontology_name", ""),
        fetched=doc.get("fetched", ""),
        by_code=doc.get("by_code", {}),
        by_name=doc.get("by_name", {}),
        by_legacy=doc.get("by_legacy", {}),
        accepted=doc.get("accepted", {}))
