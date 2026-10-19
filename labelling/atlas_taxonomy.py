"""Offline, source-qualified taxonomy and prediction joins for photo catalogues."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter
from pathlib import Path

PROJECT = "k-central-america"


def canonical_frame(key):
    """Join the documented filename aliases, rejecting collisions at each input."""
    if not isinstance(key, str) or not key.strip():
        raise ValueError("Frame key must be a nonempty string")
    name = key.rsplit("/", 1)[-1].removeprefix("comb_")
    return name[:-4] if name.lower().endswith(".jpg") else name


def unique_frames(pairs, source):
    result = {}
    for key, value in pairs:
        alias = canonical_frame(key)
        if alias in result:
            raise ValueError(f"Canonical frame collision in {source}: {key}")
        result[alias] = value
    return result


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def decode_json(payload, source):
    """Reject duplicate JSON keys and nonfinite numbers, including optional files."""

    def pairs(items):
        out = {}
        for key, value in items:
            if key in out:
                raise ValueError(f"Duplicate JSON key in {source}: {key}")
            out[key] = value
        return out

    def constant(value):
        raise ValueError(f"Nonfinite JSON number in {source}: {value}")

    return json.loads(payload, object_pairs_hook=pairs, parse_constant=constant)


def read_json(path):
    return decode_json(Path(path).read_text(), path)


def text(value, field):
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"{field} must be a string or null")
    return value.strip() or None


def identifier(value, field):
    if value is None or value == "":
        return None
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise TypeError(f"Invalid {field}")
    value = str(value).strip()
    if not value or not value.isdigit() or int(value) <= 0:
        raise ValueError(f"Invalid {field}: {value}")
    return str(int(value))


class Taxonomy:
    """Resolve explicit checklist parents and optional recorded-name crosswalks."""

    def __init__(self, checklist=None, keys=None, wcvp=None):
        self.taxa = {}
        self.by_id, self.by_name, self.genera, self.families = {}, {}, {}, {}
        self.keys = {} if keys is None else keys
        self.wcvp = {} if wcvp is None else wcvp
        if not isinstance(self.keys, dict) or not isinstance(self.wcvp, dict):
            raise TypeError("Taxonomy sidecars must be objects")
        for section in ("by_name", "by_legacy", "by_code", "accepted"):
            mapping = self.keys.get(section, {})
            if not isinstance(mapping, dict):
                raise TypeError(f"Invalid GBIF sidecar {section}")
            for value in mapping.values():
                identifier(value, section)
        for name, record in self.wcvp.items():
            if not isinstance(record, dict):
                raise TypeError(f"Invalid WCVP record: {name}")
            for field in ("rank", "family", "accepted_name"):
                text(record.get(field), "WCVP " + field)
            identifier(record.get("gbif_key"), "WCVP dataset key")
        for key in self.keys.get("accepted", {}):
            self.accepted(key)
        self.checklist_available = checklist is not None
        if checklist is not None:
            self._checklist(checklist)

    def accepted(self, value):
        key = identifier(value, "GBIF ID")
        seen = set()
        while key is not None:
            if key in seen:
                raise ValueError("Cyclic accepted GBIF IDs")
            seen.add(key)
            other = identifier(
                self.keys.get("accepted", {}).get(key, key), "accepted GBIF ID"
            )
            if other == key:
                return key
            key = other
        return None

    def add(self, taxon_id, name, rank, parent):
        row = {"id": taxon_id, "name": name, "rank": rank, "parent": parent}
        if taxon_id in self.taxa and self.taxa[taxon_id] != row:
            raise ValueError(f"Conflicting taxonomy for {taxon_id}")
        self.taxa[taxon_id] = row
        return taxon_id

    def family(self, name):
        return self.add("local:family:" + name, name, "family", None)

    def genus(self, name, family):
        parent = self.family(family)
        previous = self.genera.get(name)
        if previous is not None and previous != family:
            raise ValueError(f"Conflicting taxonomy parents for genus {name}")
        self.genera[name] = family
        return self.add("local:genus:" + name, name, "genus", parent)

    def _checklist(self, doc):
        if not isinstance(doc, dict) or doc.get("project") != PROJECT:
            raise ValueError(
                "Taxonomy checklist project must identify k-central-america"
            )
        rows = doc.get("species")
        if not isinstance(rows, list):
            raise TypeError("Checklist species must be an array")
        for field in ("n_returned", "declared_species_count"):
            count = doc.get(field)
            if count is not None and (type(count) is not int or count != len(rows)):
                raise ValueError("Incomplete checklist: counts disagree")
        grouped, raw_ids, names = {}, set(), set()
        for row in rows:
            if not isinstance(row, dict):
                raise TypeError("Invalid checklist species")
            name = text(row.get("scientificNameWithoutAuthor"), "species name")
            genus = text(row.get("genus"), "checklist genus")
            family = text(row.get("family"), "checklist family")
            gbif = identifier(row.get("gbifId"), "GBIF ID")
            pn = identifier(row.get("id"), "Pl@ntNet ID")
            if not name or not (gbif or pn):
                raise ValueError("Checklist species requires name and source ID")
            raw_id = "gbif:" + gbif if gbif else "plantnet:" + pn
            if raw_id in raw_ids or name.casefold() in names:
                raise ValueError(f"Taxonomy ID/name collision: {name}")
            raw_ids.add(raw_id)
            names.add(name.casefold())
            accepted = self.accepted(gbif)
            taxon_id = "gbif:" + accepted if accepted else "plantnet:" + pn
            record = (name, genus, family, gbif)
            group = grouped.setdefault(taxon_id, [])
            if group and group[0][1:3] != record[1:3]:
                raise ValueError(f"Conflicting taxonomy for {taxon_id}")
            group.append(record)
        for taxon_id, records in grouped.items():
            accepted = taxon_id.removeprefix("gbif:")
            chosen = next((r for r in records if r[3] == accepted), records[0])
            name, genus, family, _ = chosen
            parent = self.genus(genus, family) if genus and family else None
            self.add(taxon_id, name, "species", parent)
            for alias, _, _, gbif in records:
                self.by_name[alias.casefold()] = taxon_id
                if gbif:
                    self.by_id[gbif] = taxon_id
            if taxon_id.startswith("gbif:"):
                self.by_id[accepted] = taxon_id
            if family:
                self.families[family.casefold()] = self.family(family)

    def prediction(self, gbif):
        key = self.accepted(gbif)
        found = self.by_id.get(key) if key else None
        if found and self.taxa[found]["parent"]:
            return found
        return None

    def recorded(self, label):
        if not label:
            return None, "missing"
        metadata = self.wcvp.get(label)
        if re.search(r"(?:^|[ _])(?:var|subsp)\.", label):
            return None, "unresolved"
        if metadata and metadata.get("rank") not in (
            None,
            "SPECIES",
            "GENUS",
            "FAMILY",
        ):
            return None, "unresolved"
        # Labelbox's accepted backbone keys survive spelling and synonym changes.
        key = None
        # These are explicit Labelbox ontology codes, not parsed taxonomic ranks.
        parts = label.split("-")
        codes = []
        while len(parts) > 1 and re.fullmatch(r"[A-Z0-9]{2,}", parts[-1]):
            codes.append(parts.pop())
        for code in codes:
            value = self.keys.get("by_code", {}).get(code)
            if value is not None:
                key = self.prediction(value)
                if key:
                    return key, "ok"
        lookup_name = "-".join(parts).strip()
        for section in ("by_name", "by_legacy"):
            value = self.keys.get(section, {}).get(lookup_name.casefold())
            if value is not None:
                key = self.prediction(value)
                if key:
                    return key, "ok"
        if lookup_name.casefold() in self.by_name:
            key = self.by_name[lookup_name.casefold()]
            return key, "ok" if self.taxa[key]["parent"] else "unresolved"
        if label.casefold() in self.families:
            return self.families[label.casefold()], "ok"
        genus = next((g for g in self.genera if g.casefold() == label.casefold()), None)
        if genus:
            return "local:genus:" + genus, "ok"
        if metadata:
            rank = text(metadata.get("rank"), "WCVP rank")
            if rank == "FAMILY":
                return self.family(label), "ok"
            if rank == "GENUS":
                family = text(metadata.get("family"), "WCVP family")
                if family:
                    return self.genus(label, family), "ok"
                key = self.add("local:genus:" + label, label, "genus", None)
                return key, "unresolved"
            # WCVP dataset keys are not GBIF backbone identifiers. Never conflate.
            if rank == "SPECIES":
                wcvp_key = identifier(metadata.get("gbif_key"), "WCVP dataset key")
                if wcvp_key:
                    family = text(metadata.get("family"), "WCVP family")
                    name = (
                        text(metadata.get("accepted_name"), "WCVP accepted name")
                        or label
                    )
                    parent = self.family(family) if family else None
                    key = self.add("wcvp:" + wcvp_key, name, "species", parent)
                    return key, "ok" if parent else "unresolved"
        return None, "unresolved"

    def used(self, references):
        used = set()
        for key in references:
            while key and key not in used:
                used.add(key)
                key = self.taxa[key]["parent"]
        return [self.taxa[key] for key in sorted(used)]


def prediction_record(entry, taxonomy):
    """Return top returned candidate, preserving ties and its separate provenance."""
    if not isinstance(entry, dict):
        raise TypeError("Prediction cache entry must be an object")
    project = text(entry.get("project"), "prediction project")
    source = text(entry.get("project_source"), "prediction project source")
    if project and project != PROJECT:
        raise ValueError(f"Foreign prediction project: {project}")
    if source not in (None, "recorded", "assumed"):
        raise ValueError("Invalid prediction project source")
    raw = entry.get("raw")
    if raw is not None and not isinstance(raw, dict):
        raise ValueError("Prediction raw response must be an object")
    versions = {
        text(v, "prediction version")
        for v in (
            entry.get("model_version"),
            entry.get("version"),
            (raw or {}).get("version"),
        )
    }
    versions.discard(None)
    if len(versions) > 1:
        raise ValueError("Conflicting prediction versions")
    result = {
        "status": "empty",
        "name": None,
        "taxon": None,
        "score": None,
        "version": next(iter(versions), None),
        "project": project,
        "project_source": source,
        "tied": False,
    }
    rows = entry.get("results")
    if isinstance(rows, dict):
        rows = rows.get("species")
        shape = "survey"
    else:
        shape = "identify"
    if not isinstance(rows, list):
        raise TypeError("Prediction results must contain a candidate array")
    candidates = []
    for row in rows:
        if not isinstance(row, dict):
            raise TypeError("Invalid prediction candidate")
        name = text(
            row.get("binomial" if shape == "survey" else "scientific_name"),
            "prediction name",
        )
        score = row.get("max_score" if shape == "survey" else "score")
        if (
            type(score) not in (int, float)
            or not math.isfinite(score)
            or not 0 <= score <= 1
        ):
            raise ValueError("Prediction score must be finite and between zero and one")
        gbif = identifier(row.get("gbif_id"), "prediction GBIF ID")
        if candidates and score > candidates[-1][1]:
            raise ValueError("Prediction candidates are not in returned score order")
        candidates.append((name, score, gbif))
    if not candidates:
        return result
    name, score, gbif = candidates[0]
    taxon = taxonomy.prediction(gbif) if project == PROJECT else None
    result.update(
        status="ok" if taxon and name else "unresolved",
        name=name,
        score=score,
        taxon=taxon,
        tied=len(candidates) > 1 and score == candidates[1][1],
    )
    return result


def load_predictions(directory, taxonomy):
    """Hash every cache file, including ones outside the photo catalogue."""
    directory = Path(directory)
    available = directory.exists()
    if available and not directory.is_dir():
        raise ValueError("Prediction cache source must be a directory")
    entries, manifest = [], []
    projects, sources, versions = Counter(), Counter(), Counter()
    unknown = 0
    for path in sorted(directory.glob("*.json")):
        entry = read_json(path)
        record = prediction_record(entry, taxonomy)
        alias = canonical_frame(path.name.removesuffix(".json"))
        if entry.get("global_key") and canonical_frame(entry["global_key"]) != alias:
            raise ValueError(f"Prediction filename/global_key mismatch: {path.name}")
        entries.append((path.name.removesuffix(".json"), record))
        manifest.append({"file": path.name, "sha256": digest(path)})
        projects[record["project"] or "unknown"] += 1
        sources[record["project_source"] or "unknown"] += 1
        if record["version"]:
            versions[record["version"]] += 1
        else:
            unknown += 1
    manifest_hash = hashlib.sha256(
        json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return unique_frames(entries, "prediction cache"), {
        "available": available,
        "project": PROJECT,
        "projects": dict(projects),
        "project_sources": dict(sources),
        "versions": dict(versions),
        "unknown_version_count": unknown,
        "files": manifest,
        "manifest_sha256": manifest_hash,
    }
