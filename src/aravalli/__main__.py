"""
Main entry point for running aravalli as a module.

Usage:
    python -m aravalli run --help
    python -m aravalli profile --help
"""

from .cli import main

if __name__ == "__main__":
    main()
