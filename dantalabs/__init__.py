"""
DantaLabs SDK Top-Level Package
"""

# Import submodules to make them available directly after importing dantalabs
# e.g., allows `dantalabs.maestro` and `dantalabs.cli`
from . import maestro
from . import cli

# You could potentially expose the most common Maestro client here for convenience,
# but keeping it under the submodule is cleaner for organization:
from .maestro import MaestroClient # <-- Allow dantalabs.MaestroClient

# Define the overall package version for 'dantalabs'
__version__ = "0.1.0"

# Define what `from dantalabs import *` imports (optional, often discouraged)
__all__ = ["maestro", "cli", "MaestroClient", "__version__"]