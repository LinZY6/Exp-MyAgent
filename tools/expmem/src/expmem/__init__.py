"""Experiment memory for Agents: search papers, retrieve past trials, record new ones."""

from expmem.literature import search_literature
from expmem.node import ExperimentNode, Outcome, PaperRef
from expmem.service import ExperimentLab
from expmem.store import ExperimentStore

__version__ = "0.1.0"
__all__ = [
    "ExperimentLab",
    "ExperimentNode",
    "ExperimentStore",
    "Outcome",
    "PaperRef",
    "search_literature",
]
