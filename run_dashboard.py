"""Entry point for the Rappi Competitive Intelligence dashboard.

Usage:
    python run_dashboard.py              # recommended
    streamlit run dashboard/app.py       # alternative
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent
DASHBOARD_APP = ROOT / "dashboard" / "app.py"
PORT = 8504


def main() -> None:
    print(f"\n[Rappi] Dashboard -> http://localhost:{PORT}/\n")
    subprocess.run(
        [
            sys.executable, "-m", "streamlit", "run", str(DASHBOARD_APP),
            "--server.port", str(PORT),
            "--server.headless", "false",
            "--browser.gatherUsageStats", "false",
        ],
        check=True,
    )


if __name__ == "__main__":
    main()
