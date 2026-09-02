# bci-dashboard

## Remote
- Single remote `origin` → `traitlab/bci-dashboard`. No fork. Push feature branches, never to `main` directly.

## Hard constraints
- `dashboard/` is **stdlib only**. No pandas, numpy, template engine, or web framework. Third-party imports there are a breaking change.
- `predict/` and `labelling/` may use `requirements.txt` packages. `numpy`/`pandas` only on the `aggregate_survey.py` path.
- Building a page makes no network call and reads no credential. Fetch is a separate step.
- Crop/box geometry is read from what the fetch recorded, never recomputed from a constant.
- A published number carries its population and support count. Gated and ungated are reported side by side.

## Build and test
```bash
.venv/bin/pytest
bin/refresh.sh                    # export -> GT merge -> measure -> rebuild -> snapshot
```
A change to what a number means updates `bci-dashboard-docs/metrics.md`, in the sibling directory, in the same session.

## Which skills to use
- Feature-sized work: Spec Kit. `/speckit-specify` → `/speckit-clarify` → `/speckit-plan` → `/speckit-tasks` → `/speckit-implement`. Artifacts in `specs/NNN-slug/`, gitignored and local to the checkout.
- Debugging, small fixes, refactors: `superpowers:systematic-debugging` and `debugging-discipline`. Do not open a spec for these.
- Project principles live in `.specify/memory/constitution.md`. `/speckit-plan` checks against it.

## Gotchas
- `data/`, `snapshots/`, `build/` are generated and gitignored. `input/boxes/` is tracked: the frame list defines the population.
- `.claude/` is covered by the global gitignore, so speckit skills are local-only. A collaborator needs `specify init --here --integration claude` to get them.
- Species absence in cached top-5 lists is not evidence the model cannot name a species. Out-of-scope and in-checklist misses are different populations.
