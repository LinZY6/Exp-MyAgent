"""CPU Friedman #1 lab: fit specs, never write the experiment ledger."""

from fnfit.fit import run_spec
from fnfit.tools import handle
from fnfit.world import COLLECTION, PRIMARY

__all__ = ["COLLECTION", "PRIMARY", "handle", "run_spec"]
