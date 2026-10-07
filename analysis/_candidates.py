"""Candidate copies of ship-decision tables.

Some runtime tables encode decisions (which cells a live gate fires on,
which L3 cells skip). Their Stage 1/2 tools re-pick the cell set every
day, but a daily-churning set must not go live on its own. Those tools
write here instead of weather_collector/data/; the runtime copy in the
repo changes only through a ship (copy the candidate over, bump, deploy).

Tables meant to refit on their own go through the cloud refitter instead
(refitter/tables.py).
"""
import os

CANDIDATE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output", "candidates")


def candidate_path(name):
    os.makedirs(CANDIDATE_DIR, exist_ok=True)
    return os.path.join(CANDIDATE_DIR, name)
