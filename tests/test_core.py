def test_status_precedence_is_the_order_diagnose_actually_uses(core):
    """The pages print the precedence, so it has to be the real one. Each row
    below satisfies every rule from its position onward that can hold at once,
    so the status it gets is proof that its own rule was checked first."""
    def row(**kw):
        base = dict(n_labelled_frames=1, top1_accuracy=0.0, top5_accuracy=0.0,
                    in_corpus_vocabulary=True, in_project_checklist=None)
        base.update(kw)
        return base

    # Satisfies out_of_scope, reliable, ranking and unreachable at once.
    everything = row(in_project_checklist=False, in_corpus_vocabulary=False,
                     n_labelled_frames=99, top1_accuracy=1.0, top5_accuracy=1.0)
    assert core.diagnose(everything) == "out_of_scope"
    # Reliable and ranking cannot both hold: reliable needs a1 high, ranking
    # needs a5 - a1 wide.
    assert core.diagnose(row(n_labelled_frames=99, top1_accuracy=1.0,
                             top5_accuracy=1.0)) == "reliable"
    assert core.diagnose(row(n_labelled_frames=1, top1_accuracy=0.0,
                             top5_accuracy=1.0)) == "ranking"
    # unreachable no longer outranks reliable or ranking: the same rows that
    # would have won it before, minus in_corpus_vocabulary, still go to
    # whichever of those fits.
    assert core.diagnose(row(in_corpus_vocabulary=False, n_labelled_frames=99,
                             top1_accuracy=1.0, top5_accuracy=1.0)) == "reliable"
    assert core.diagnose(row(in_corpus_vocabulary=False, n_labelled_frames=1,
                             top1_accuracy=0.0, top5_accuracy=1.0)) == "ranking"
    # unreachable still outranks unmeasured.
    assert core.diagnose(row(in_corpus_vocabulary=False, n_labelled_frames=1,
                             top1_accuracy=0.0, top5_accuracy=0.0)) == "unreachable"
    assert core.diagnose(row(n_labelled_frames=1)) == "unmeasured"
    assert core.STATUS_PRECEDENCE == (
        "out_of_scope", "reliable", "ranking", "unreachable", "unmeasured")


def test_out_of_scope_requires_a_checklist_to_say_false_not_just_absent(core):
    """``None`` (no checklist on disk) is not the same claim as ``False``
    (checklist read, species absent). Only ``False`` reaches out_of_scope."""
    row = dict(n_labelled_frames=1, top1_accuracy=0.0, top5_accuracy=0.0,
              in_corpus_vocabulary=False, in_project_checklist=None)
    assert core.diagnose(row) == "unreachable"
    row["in_project_checklist"] = False
    assert core.diagnose(row) == "out_of_scope"


def test_summarise_gives_help_one_sentence_not_the_whole_module_docstring(core):
    """--help printed nine lines of design note, RST backticks and a usage line
    argparse prints for itself, before the first flag."""
    doc = """One line saying what this is.

    ``sibling.py`` does the other thing.

        python3 dashboard/build_external.py [--out PATH]
    """
    assert core.summarise(doc) == "One line saying what this is."


def test_a_rate_gap_that_is_exact_in_arithmetic_is_not_lost_to_binary(core):
    """63/85 and 80/85 differ by exactly RANKING_MIN_GAP, and by one float step
    less in binary. The species is "one confirmation away" either way."""
    row = {"n_labelled_frames": 85, "top1_accuracy": 63 / 85, "top5_accuracy": 80 / 85,
           "in_corpus_vocabulary": True, "in_project_checklist": True}
    assert (80 / 85) - (63 / 85) < core.RANKING_MIN_GAP
    assert core.diagnose(row) == "ranking"
    row = {"n_labelled_frames": 5, "top1_accuracy": 4 / 5, "top5_accuracy": 5 / 5,
           "in_corpus_vocabulary": True, "in_project_checklist": True}
    assert core.diagnose(row) == "ranking"
