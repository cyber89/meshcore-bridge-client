try:
    from ._version import version as __version__
except ImportError:
    try:
        from importlib.metadata import version

        __version__ = version("openhop_repeater")
    except Exception:
        __version__ = "unknown"
