"""Toy collections for retrieval contrast."""

__all__ = ["DATA_ROOT", "PROBE", "build_rec_ctr", "build_seq_recall"]


def __getattr__(name: str):
    if name in __all__:
        from expmem.datasets.build import DATA_ROOT, PROBE, build_rec_ctr, build_seq_recall

        return {
            "DATA_ROOT": DATA_ROOT,
            "PROBE": PROBE,
            "build_rec_ctr": build_rec_ctr,
            "build_seq_recall": build_seq_recall,
        }[name]
    raise AttributeError(name)
