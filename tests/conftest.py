"""Make shared test fixtures importable as ``fixtures.*`` from any test directory."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
