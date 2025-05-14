"""
DantaLabs SDK Top-Level Package
"""

# Import submodules to make them available directly after importing dantalabs
# e.g., allows `dantalabs.maestro`
from . import maestro

# You could potentially expose the most common Maestro client here for convenience,
# but keeping it under the submodule is cleaner for organization:
# from .maestro import MaestroClient # <-- Alternative, allows dantalabs.MaestroClient

# Define the overall package version for 'dantalabs'
__version__ = "0.1.0"

# Define what `from dantalabs import *` imports (optional, often discouraged)
__all__ = ["maestro", "__version__"]