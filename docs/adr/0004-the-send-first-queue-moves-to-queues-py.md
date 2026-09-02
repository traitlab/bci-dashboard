# ADR 0004: the send-first queue moves out of `core.py` into `queues.py`

- Status: accepted
- Date: 2026-09-02

## Context

`core.py` says what it is in its first line: "the vocabulary every other module
works in". Paths, thresholds, name handling, and the small helpers that turn
counts into the strings a page prints.

The send-first queue was in there too: `QUEUE_ORDER`, `BATCH_SIZE`,
`queue_of_prediction`, `chunk_send_batches`, `send_first_rows`, and the two
CSV column orders. That is not vocabulary. It is a decision procedure, with its
own tests (`test_queueing.py`, `test_batches.py`) and its own reason to change,
which is a botanist saying the queue sends the wrong photos first.

The file was 517 lines. `CLAUDE.md` says to keep files under 500.

## Decision

Those seven names move to `dashboard/queues.py`, which imports its five
thresholds from `core`. `core.py` drops to 408 lines and its opening claim is
true again.

## Rationale

The boundary falls where the maintenance differs. Changing `LOW_CONF` is a
change to what "unsure" means, and every page that prints a confidence answers
to it. Changing `queue_of_prediction` is a change to what gets labelled next,
and nothing outside the queue notices. The thresholds stay in `core` for that
reason: they are read by `run_log.py` and the page builders as well.

One import edge is created, `queues` -> `core`, and it runs the same direction
as every other module's. There is no cycle to introduce, because `core` imports
no sibling at all and this change does not give it one.

`SEND_FIRST_COLUMNS` and `SEND_BATCH_COLUMNS` came with it. They were added the
same day, when `measure.py` was found writing a header whose order
`chunk_send_batches` separately indexed by position. Their home is beside the
batcher that reads them, not beside the paths.

## What this ADR does not cover

`core.py` stays one module otherwise. The name handling, the loaders and the
crop-coverage gate all have callers in `predict/` and `labelling/` as well as
`dashboard/`, and splitting them would hand four import lists to every one of
those callers for no check gained.
