"""MetaBridge OS capture & input agent package."""

from .capture import capture_window_once, publish_loop, synthetic_frame
from .input_agent import InputAgent

__all__ = ["InputAgent", "capture_window_once", "publish_loop", "synthetic_frame"]
