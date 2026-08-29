"""VideoResolver plugin entry point."""

import importlib

from gsuid_core.sv import Plugins

Plugins(
    name="VideoResolver",
    force_prefix=["vr"],
    allow_empty_prefix=False,
    alias=["resolver", "视频解析"],
)

importlib.import_module(f"{__name__}.handlers")
