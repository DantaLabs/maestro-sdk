from .client import MaestroClient
from .memory import ManagedMemory
from .exceptions import (
    MaestroError,
    MaestroApiError,
    MaestroAuthError,
    MaestroValidationError
)

# Optionally expose key models module
# from . import models

# Define a version specific to the maestro component if needed,
# although the main package version is usually sufficient.
__version__ = "0.1.0" # Matches top-level for now

__all__ = [
    "MaestroClient",
    "ManagedMemory",
    "MaestroError",
    "MaestroApiError",
    "MaestroAuthError",
    "MaestroValidationError",
    "__version__",
    # "models",
]