"""Independent image monitoring project; no network or GUI activity on import."""

from importlib.resources import files

PUBLIC_VERSION = files(__name__).joinpath("VERSION").read_text(encoding="ascii").strip()
