"""Signal-only runner - runs filter+signal pipeline without report/Discord."""
import sys
from pathlib import Path

if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    # Signal-only mode: add --skip-discord and delegate to main
    if "--skip-discord" not in sys.argv:
        sys.argv.append("--skip-discord")
    import main as _main
    _main.main()
