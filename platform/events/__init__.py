__all__ = [
    "build_envelope",
    "load_event_taxonomy",
    "load_topic_index",
    "validate_envelope_payload",
]


def __getattr__(name: str):
    if name not in __all__:
        raise AttributeError(name)
    from .taxonomy import (
        build_envelope,
        load_event_taxonomy,
        load_topic_index,
        validate_envelope_payload,
    )

    exports = {
        "build_envelope": build_envelope,
        "load_event_taxonomy": load_event_taxonomy,
        "load_topic_index": load_topic_index,
        "validate_envelope_payload": validate_envelope_payload,
    }
    return exports[name]
