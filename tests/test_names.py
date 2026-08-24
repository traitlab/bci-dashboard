"""Name reconciliation, the join every published number depends on.

A box label that does not compare equal to a GT species name is not a visible
failure: it degrades into a diagnostic saying the crop is filled by some other
species. So the cases here are the ones the box CSV actually contains, not
invented ones.

    python -m unittest discover tests
"""

import importlib.util
import pathlib
import sys
import unittest

REPO = pathlib.Path(__file__).resolve().parents[1]


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod          # a @dataclass in core.py needs this
    spec.loader.exec_module(mod)
    return mod


core = _load("_core_under_test", REPO / "dashboard" / "core.py")


class StripCollectionCodes(unittest.TestCase):
    def test_two_codes_both_come_off(self):
        # The common shape: a 6-char code followed by a 4-char one.
        self.assertEqual(
            core.strip_collection_codes("Hura crepitans-HURACR-HURC"),
            "hura crepitans",
        )

    def test_short_second_code(self):
        # '-ANAE' is 4 characters, below what normalize() alone recognises.
        self.assertEqual(
            core.strip_collection_codes("Anacardium excelsum-ANACEX-ANAE"),
            "anacardium excelsum",
        )

    def test_code_with_a_digit(self):
        self.assertEqual(
            core.strip_collection_codes("Luehea seemannii-LUEHSE-LUE1"),
            "luehea seemannii",
        )

    def test_single_code(self):
        self.assertEqual(
            core.strip_collection_codes("Quararibea asterolepis-QUARAS"),
            "quararibea asterolepis",
        )

    def test_genus_only_label_is_untouched(self):
        self.assertEqual(core.strip_collection_codes("Alseis"), "alseis")

    def test_hyphenated_epithet_survives(self):
        # The reason codes are matched on upper case: lowering first would make
        # '-cati' indistinguishable from a collection code.
        self.assertEqual(
            core.strip_collection_codes("Macfadyena unguis-cati-MACFUN-MACU"),
            "macfadyena unguis-cati",
        )

    def test_empty_and_none(self):
        self.assertEqual(core.strip_collection_codes(""), "")
        self.assertEqual(core.strip_collection_codes(None), "")

    def test_every_label_in_the_box_csv_resolves(self):
        """After stripping, the only hyphen left in the corpus is a real epithet.

        A leftover hyphen cannot be told from a lowered collection code by shape
        alone, so the legitimate cases are pinned by name. A new one appearing
        means either a new epithet or a code shape the stripper misses, and both
        are worth a look before the numbers ship.
        """
        import csv

        path = REPO / "input" / "boxes" / "crop_bounding_boxes.csv"
        if not path.exists():
            self.skipTest("box CSV not present")
        with path.open(newline="", encoding="utf-8") as fh:
            labels = {r["lb_label"] for r in csv.DictReader(fh)}
        hyphenated_epithets = {"macfadyena unguis-cati"}
        left = sorted(
            s for s in (core.strip_collection_codes(x) for x in labels)
            if "-" in s and s not in hyphenated_epithets
        )
        self.assertEqual(left, [], f"{len(left)} labels still carry a code")


class CropDominantIsComparable(unittest.TestCase):
    """The gate's dominant name has to be in the same vocabulary as the GT label.

    It is not enough for the stripper to be correct: crop_overlap has to call it
    instead of normalize(), because normalize() lowers the string and a lowered
    collection code cannot be stripped afterwards. That regression is silent. The
    gate still admits the same frames, and only the 'crop-dominant differs from
    the GT label' diagnostic moves, from about 10% to about 99%.
    """

    def setUp(self):
        if not (REPO / "input" / "boxes" / "crop_bounding_boxes.csv").exists():
            self.skipTest("box CSV not present")
        sys.path.insert(0, str(REPO / "dashboard"))
        self.addCleanup(sys.path.remove, str(REPO / "dashboard"))
        import crop_overlap
        self.frames, _ = crop_overlap.build()

    def test_dominant_names_carry_no_collection_code(self):
        # A code that survived lowering shows up as a trailing hyphen group of
        # letters and digits that is not a real epithet.
        import re
        suspect = sorted({
            f["dominant"] for f in self.frames.values()
            if f["dominant"] and re.search(r"-[a-z]*\d", f["dominant"])
        })
        self.assertEqual(suspect, [])

    def test_dominant_names_mostly_exist_in_the_gt_vocabulary(self):
        """A name that no GT record uses is either a real disagreement about what
        fills the crop or a broken join. Real disagreement cannot reach half."""
        import csv
        gt = {
            core.normalize(r["wcvp_canonical_name"])
            for r in csv.DictReader((REPO / "data" / "gt_dominant_taxon.csv").open())
            if (r["wcvp_canonical_name"] or "").strip()
        }
        dom = [f["dominant"] for f in self.frames.values() if f["dominant"]]
        unknown = sum(1 for d in dom if d not in gt)
        self.assertLess(unknown / len(dom), 0.5,
                        f"{unknown}/{len(dom)} dominant names unknown to the GT set")


class Normalize(unittest.TestCase):
    def test_accents_and_case(self):
        self.assertEqual(core.normalize("Öcotea  Leptobotra"), "ocotea leptobotra")

    def test_underscores_become_spaces(self):
        self.assertEqual(core.normalize("Hura_crepitans"), "hura crepitans")

    def test_infraspecific_rank_removed(self):
        self.assertEqual(
            core.normalize("Inga edulis var. grandiflora"), "inga edulis"
        )


class CanonicalBinomial(unittest.TestCase):
    def test_authored_name_reduced(self):
        self.assertEqual(
            core.canonical_binomial("Ocotea leptobotra (Ruiz & Pav.) Mez"),
            "Ocotea leptobotra",
        )

    def test_genus_alone_is_not_a_binomial(self):
        self.assertIsNone(core.canonical_binomial("Ocotea"))

    def test_empty(self):
        self.assertIsNone(core.canonical_binomial(""))
        self.assertIsNone(core.canonical_binomial(None))


class SpeciesLevel(unittest.TestCase):
    def test_binomial_is_species_level(self):
        self.assertTrue(core.is_species_level("hura crepitans"))

    def test_genus_is_not(self):
        self.assertFalse(core.is_species_level("hura"))


if __name__ == "__main__":
    unittest.main()
