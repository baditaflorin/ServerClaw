from .schema import ChangedObject, SemanticDiff

__all__ = ["ChangedObject", "DiffEngine", "SemanticDiff"]


def __getattr__(name: str):
    if name == "DiffEngine":
        from .engine import DiffEngine

        return DiffEngine
    raise AttributeError(name)
