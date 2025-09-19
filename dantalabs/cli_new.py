#!/usr/bin/env python3
"""
Main entry point for the DantaLabs Maestro CLI.
This replaces the old monolithic cli.py file with a modular structure.
"""

from .cli.app import app

if __name__ == "__main__":
    app()