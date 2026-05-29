"""Project-level conftest: ensure local `src/` on sys.path so tests
run without `pip install -e .` (useful in network-restricted envs).

Also adds sibling `lab-executor-mcp` src if present (worktree layout)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if SRC.exists() and str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

# lab-executor sibling (development monorepo layout)
LAB_SRC = ROOT.parent / "lab-executor-mcp" / "src"
if LAB_SRC.exists() and str(LAB_SRC) not in sys.path:
    sys.path.insert(0, str(LAB_SRC))
