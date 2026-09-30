"""sensor-gap: find the nearest upstream sensor gap for a river point."""

__version__ = "0.1.0"


def main(*args, **kwargs):  # lazy import keeps `python -m sensor_gap.cli` clean
    from .cli import main as _main
    return _main(*args, **kwargs)


__all__ = ["main", "__version__"]
