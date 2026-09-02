"""Which botanist labels the model could name at all, tier by tier.

`reconcile_names` sorts every label into five tiers against the names the cache
returned, and the last two are the ceiling both pages report: a species absent
from every list is one no amount of labelling can fix, and a label that stops at
the genus is one no species rate can be measured on. The whole "what labelling
cannot fix" panel is this function's output.

It had no test. The tiers are ordered, first match wins, and the order is the
claim: a name matched byte-for-byte is a stronger statement than one matched
after accents and case were stripped, which is stronger than one reached only
through a WCVP synonym.

Every case here is built from two-name inputs rather than a snapshot, so it runs
on a fresh clone.

    .venv/bin/pytest tests/test_reconcile.py
"""

from __future__ import annotations

from collections import Counter


def _run(health, core, labels, predicted, crosswalk=None):
    """Reconcile `labels` against a cache that returned `predicted`.

    `predicted` is one photo's ranked list, which is all the tiers read: they
    ask whether a name appears anywhere in the cache, not where.
    """
    gt_rows = [{"wcvp_canonical_name": n} for n in labels]
    predictions = {"photo": [(b, 1.0) for b in predicted]}
    vocab = Counter(core.normalize(b) for b in predicted)
    return health.reconcile_names(gt_rows, predictions, vocab, crosswalk or {})


def _tier(health, core, label, predicted, crosswalk=None):
    return _run(health, core, [label], predicted, crosswalk).tier_of_name[label]


# ---------------------------------------------------------------------------
# The five tiers
# ---------------------------------------------------------------------------

def test_a_byte_exact_name_is_the_strongest_tier(health, core):
    assert _tier(health, core, "Ficus insipida", ["Ficus insipida"]) == "a_exact_binomial"


def test_a_name_matching_only_after_normalising_is_a_weaker_tier(health, core):
    """Accents and case are stripped to match, so the claim is weaker than a
    byte-exact one and the page reports it separately."""
    assert _tier(health, core, "FICUS INSÍPIDA", ["Ficus insipida"]) == "b_normalized"


def test_a_synonym_is_reached_only_through_the_crosswalk(health, core):
    """Without the WCVP file the same label is absent from the corpus. The
    crosswalk is what turns a ceiling into a match, so its absence must not
    look like a match. A cross-genus synonym, which many are, so that dropping
    the crosswalk leaves nothing else to match on."""
    cw = {core.normalize("Bombacopsis quinata"): core.normalize("Pachira quinata")}
    assert _tier(health, core, "Bombacopsis quinata", ["Pachira quinata"], cw) == (
        "d_wcvp_synonym")
    assert _tier(health, core, "Bombacopsis quinata", ["Pachira quinata"]) == (
        "e_absent_from_corpus")


def test_a_label_that_stops_at_the_genus_is_its_own_tier_before_any_matching(health, core):
    """Checked first, so a one-word label cannot be reported as an exact match
    even when the cache returned that exact word. No species rate can be
    measured on it either way."""
    assert _tier(health, core, "Ficus", ["Ficus"]) == "c_gt_label_is_genus_only"


def test_a_species_we_only_have_the_genus_for_is_not_absent(health, core):
    """The distinction the ceiling panel rests on. Pl@ntNet knows the genus but
    has never returned this species, which is a different ceiling from a genus
    it has never returned at all."""
    assert _tier(health, core, "Ficus insipida", ["Ficus obtusifolia"]) == "c_genus_only_in_corpus"
    assert _tier(health, core, "Ficus insipida", ["Cecropia peltata"]) == "e_absent_from_corpus"


def test_the_genus_checked_is_the_one_the_crosswalk_maps_to(health, core):
    """A synonym whose accepted name sits in a genus the cache knows is a
    genus-only match, not an absence. Reading the genus off the raw label
    instead would report a ceiling that the crosswalk has already lifted."""
    cw = {core.normalize("Pseudobombax barrigon"): core.normalize("Ceiba pentandra")}
    assert _tier(health, core, "Pseudobombax barrigon", ["Ceiba aesculifolia"], cw) == (
        "c_genus_only_in_corpus")


# ---------------------------------------------------------------------------
# The counts the panels print
# ---------------------------------------------------------------------------

def test_every_label_lands_in_exactly_one_tier_and_the_counts_add_up(health, core):
    """The panel prints these as a breakdown of the whole, so a label counted
    twice or not at all makes the parts disagree with the total."""
    labels = ["Ficus insipida", "Ficus insipida", "Cecropia peltata", "Ficus",
              "Zzz nonexistent"]
    r = _run(health, core, labels, ["Ficus insipida", "Cecropia obtusifolia"])
    assert sum(r.tier_names.values()) == len(set(labels))
    assert sum(r.tier_crowns.values()) == len(labels)
    assert set(r.tier_of_name) == set(labels)


def test_crowns_are_counted_per_label_and_names_only_once(health, core):
    """`tier_names` answers "how many species", `tier_crowns` "how many
    frames". The absent-species panel states both, and they are different
    numbers whenever a species has more than one frame."""
    r = _run(health, core, ["Zzz nonexistent"] * 4, ["Ficus insipida"])
    assert r.tier_names["e_absent_from_corpus"] == 1
    assert r.tier_crowns["e_absent_from_corpus"] == 4


def test_the_three_reported_lists_carry_the_frame_count_with_each_name(health, core):
    """Each list is printed with a count beside the name, so the count travels
    in the tuple rather than being looked up again somewhere else."""
    cw = {core.normalize("Bombacopsis quinata"): core.normalize("Ficus insipida")}
    r = _run(health, core,
             ["Bombacopsis quinata"] * 2 + ["Ficus obtusifolia"] * 3 + ["Zzz nonexistent"],
             ["Ficus insipida"], cw)
    assert r.applied_synonyms == [
        ("Bombacopsis quinata", core.normalize("Ficus insipida"), 2)]
    assert [(n, c) for n, _, c in r.genus_in_corpus_only] == [("Ficus obtusifolia", 3)]
    assert [(n, c) for n, _, c in r.absent_names] == [("Zzz nonexistent", 1)]


def test_the_exact_tier_reads_the_unnormalised_predictions(health, core):
    """`corpus_raw` exists so tier (a) can be byte-exact. Built from the ranked
    lists rather than from the normalized vocabulary, or every match would be
    exact and the tiers would collapse into one."""
    r = _run(health, core, ["Ficus insipida"], ["Ficus insipida"])
    assert "Ficus insipida" in r.corpus_raw
    assert core.normalize("Ficus insipida") in r.corpus_norm
