def test_status_precedence_is_the_order_diagnose_actually_uses(core):
    """The pages print the precedence, so it has to be the real one. Each row
    below satisfies every rule from its position onward, so the status it gets
    is proof that its own rule was checked first."""
    def row(**kw):
        base = dict(n_labelled_crowns=1, top1_accuracy=0.0, top5_accuracy=0.0,
                    in_corpus_vocabulary=True)
        base.update(kw)
        return base

    # Satisfies unreachable, reliable, ranking and unmeasured at once.
    everything = row(in_corpus_vocabulary=False, n_labelled_crowns=1,
                     top1_accuracy=1.0, top5_accuracy=1.0)
    assert core.diagnose(everything) == "unreachable"
    # Reliable and ranking and unmeasured cannot all hold: reliable needs frames.
    assert core.diagnose(row(n_labelled_crowns=99, top1_accuracy=1.0,
                             top5_accuracy=1.0)) == "reliable"
    # Thin and its answer is in the list: ranking wins over unmeasured.
    assert core.diagnose(row(n_labelled_crowns=1, top1_accuracy=0.0,
                             top5_accuracy=1.0)) == "ranking"
    assert core.diagnose(row(n_labelled_crowns=1)) == "unmeasured"
    assert core.STATUS_PRECEDENCE == ("unreachable", "reliable", "ranking", "unmeasured")


def test_summarise_gives_help_one_sentence_not_the_whole_module_docstring(core):
    """--help printed nine lines of design note, RST backticks and a usage line
    argparse prints for itself, before the first flag."""
    doc = """One line saying what this is.

    ``sibling.py`` does the other thing.

        python3 dashboard/build_external.py [--out PATH]
    """
    assert core.summarise(doc) == "One line saying what this is."
