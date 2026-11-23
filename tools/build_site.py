#!/usr/bin/env python3
"""Compatibility wrapper. The generator lives in scripts/build_site.py."""
from pathlib import Path
import runpy
import sys

sys.argv[0] = str(Path(__file__).resolve().parent.parent / "scripts" / "build_site.py")
runpy.run_path(sys.argv[0], run_name="__main__")
