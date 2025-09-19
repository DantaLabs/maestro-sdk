#!/usr/bin/env python3
"""
Main entry point for the DantaLabs Maestro CLI.
This file now uses the new modular CLI structure.
"""

from .cli.app import app

if __name__ == "__main__":
    app()