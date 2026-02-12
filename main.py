#!/usr/bin/env python3
"""
Launcher so you can run from project root: python3 main.py
Delegates to src.main.
"""
import sys
from pathlib import Path

_root = Path(__file__).resolve().parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from src.main import main

if __name__ == "__main__":
    sys.exit(main())
