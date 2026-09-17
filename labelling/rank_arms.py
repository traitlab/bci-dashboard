"""Two more orders to run the audit's simulation under, beside the shipped one.

``rank_queue.py --audit`` grades "least like everything already labelled"
against a random order. Two orders sit between those poles and neither was ever
measured:

``confidence``
    Least confident first, the rule ``send_first_queue.csv`` sorted on before
    any photo vector existed. It is the order this ranking replaced, so it is
    the one a reader asks about.

``queue_then_novelty``
    What the queue page actually ships: sort the pool into the four queues
    first, then take the photos least like everything labelled inside the
    leading queue. The audit's own challenger ranks by novelty alone, with no
    queue in front of it, so its gain describes the ranking and not the order
    on the page.

Both read the first guess and its confidence from the same cached Pl@ntNet
answers the pages do, through ``dashboard/health.load_health``, and the queue
rule itself from ``dashboard/queues.queue_of_prediction``. Restating either
here would let the audit grade an order the page does not ship.

The queue arm recomputes the two per-species numbers the rule needs, the count
of labelled frames and the measured first-guess accuracy, from the frames
labelled so far in the simulation rather than from the finished corpus. Reading
the finished numbers back would tell the order at round one how well a species
it has not labelled yet turns out to be named.
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

import numpy as np
from labelfirst.strategies import REGISTRY
from labelfirst.strategies.base import SelectionResult
from labelfirst.strategies.kcenter import greedy_kcenter

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "dashboard"))

from core import GT_KEY_PREFIX  # noqa: E402
from health import load_health  # noqa: E402
from queues import QUEUE_ORDER, queue_of_prediction  # noqa: E402

CONFIDENCE_ARM = "confidence"
QUEUE_ARM = "queue_then_novelty"
ARMS = (CONFIDENCE_ARM, QUEUE_ARM)
# A frame the model answered nothing for. It cannot be sorted by a confidence
# it has not got, and it belongs to no queue, so both arms send it to the back
# rather than guess. One sentinel for both, so the two arms treat it alike.
NO_ANSWER_CONFIDENCE = float("inf")
NO_ANSWER_QUEUE = len(QUEUE_ORDER)


def frame_answers(keys: list[str]) -> tuple[np.ndarray, np.ndarray]:
    """The first guess and its confidence per frame, aligned to ``keys``.

    Names come back canonicalised the way the pages canonicalise them, since
    the queue rule looks a guess up among the labels by name.
    """
    h = load_health()
    guess = np.empty(len(keys), dtype=object)
    conf = np.empty(len(keys), dtype=np.float64)
    for i, key in enumerate(keys):
        ranked = h.predictions.get(key.removeprefix(GT_KEY_PREFIX)) or []
        guess[i] = h.canon(ranked[0][0]) if ranked else ""
        conf[i] = float(ranked[0][1]) if ranked else NO_ANSWER_CONFIDENCE
    return guess, conf


class LeastConfidentFirst:
    """Send the photo the model is least sure of. The rule before this one."""

    def __init__(self, conf: np.ndarray, seed: int = 0):
        self.name = CONFIDENCE_ARM
        self.seed = seed
        self._conf = conf

    def select(self, X: np.ndarray, *, labeled: np.ndarray, k: int) -> SelectionResult:
        pool = np.setdiff1d(np.arange(X.shape[0], dtype=np.int64), labeled)
        picks = pool[np.argsort(self._conf[pool], kind="stable")][:k]
        return SelectionResult(picks=picks.astype(np.int64),
                               metadata={"strategy": self.name, "seed": self.seed})


class QueueThenNovelty:
    """Sort into the four queues first, then by how new the photo looks.

    The page's own order. Inside the leading queue the pick is farthest-first,
    the same ``greedy_kcenter`` the ranking uses. A queue that fits inside the
    round's budget is taken whole: the audit counts species found per round,
    so the order within one round cannot move a number.
    """

    def __init__(self, guess: np.ndarray, conf: np.ndarray, labels: np.ndarray,
                 seed: int = 0):
        self.name = QUEUE_ARM
        self.seed = seed
        self._guess, self._conf, self._labels = guess, conf, labels

    def _queues(self, pool: np.ndarray, labeled: np.ndarray) -> np.ndarray:
        """Which queue each pool frame is in, judged on what is labelled now."""
        support = Counter(self._labels[labeled].tolist())
        right: Counter = Counter()
        for i in labeled:
            if self._guess[i] == self._labels[i]:
                right[self._labels[i]] += 1
        top1 = {s: right[s] / n for s, n in support.items()}
        return np.array([NO_ANSWER_QUEUE if not self._guess[i] else
                         QUEUE_ORDER.index(queue_of_prediction(
                             self._guess[i], self._conf[i], support, top1))
                         for i in pool], dtype=np.int64)

    def select(self, X: np.ndarray, *, labeled: np.ndarray, k: int) -> SelectionResult:
        pool = np.setdiff1d(np.arange(X.shape[0], dtype=np.int64), labeled)
        queues = self._queues(pool, labeled)
        rng = np.random.default_rng(self.seed)
        picks: list[int] = []
        for q in range(NO_ANSWER_QUEUE + 1):
            budget = k - len(picks)
            if budget <= 0:
                break
            members = pool[queues == q]
            if members.size <= budget:
                picks.extend(int(i) for i in members)
            else:
                picks.extend(greedy_kcenter(X, members, labeled, budget, rng))
        return SelectionResult(picks=np.asarray(picks, dtype=np.int64),
                               metadata={"strategy": self.name, "seed": self.seed})


def arm_factory(keys: list[str], labels: list[str]):
    """``(name, seed) -> Strategy`` covering the two arms and the registry.

    A name labelfirst already knows is built the way ``simulate`` would build
    it itself, so passing this factory cannot move the shipped audit's numbers.
    """
    guess, conf = frame_answers(keys)
    label_arr = np.asarray(labels, dtype=object)

    def factory(name: str, seed: int):
        if name == CONFIDENCE_ARM:
            return LeastConfidentFirst(conf, seed=seed)
        if name == QUEUE_ARM:
            return QueueThenNovelty(guess, conf, label_arr, seed=seed)
        return REGISTRY[name](seed=seed)

    return factory
