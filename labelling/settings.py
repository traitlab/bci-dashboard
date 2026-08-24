"""Config and credential lookup for the labelling scripts.

A dataset id and a project id are not credentials: they name which workspace a
run points at and open nothing without ``LABELBOX_API_KEY``. Defaults live in
``config.yaml``; an environment variable, from the shell or ``.env``, wins:

    LABELBOX_DATASET_ID=<id> python labelling/fetch_dataset.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import yaml
from dotenv import load_dotenv

REPO = Path(__file__).resolve().parents[1]
CONFIG = REPO / "config.yaml"


def load_config() -> dict:
    """``config.yaml``, found relative to the repo rather than to the caller."""
    with open(CONFIG, encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def setting(*path: str, env: str, config: dict | None = None) -> str:
    """The value of ``env``, or ``config.yaml`` at ``path``, in that order.

    ``path`` is the nested key sequence, so ``("labelbox", "dataset_id")`` reads
    ``labelbox.dataset_id``. Exits with a message naming both sources when
    neither carries a value, because the alternative is a run that authenticates
    and then asks Labelbox for ``None``.
    """
    load_dotenv()
    value = os.environ.get(env)
    if value:
        return value

    node = load_config() if config is None else config
    for key in path:
        node = (node or {}).get(key) if isinstance(node, dict) else None
    if node:
        return str(node)

    sys.exit(f"MISSING {env}: set it in the environment or .env, or set "
             f"{'.'.join(path)} in config.yaml")


def api_key() -> str:
    """``LABELBOX_API_KEY``. This one is a credential and has no config default."""
    load_dotenv()
    key = os.environ.get("LABELBOX_API_KEY")
    if not key:
        sys.exit("MISSING LABELBOX_API_KEY: set it in the environment or .env")
    return key
