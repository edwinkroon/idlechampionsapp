"""Write build_info.py with a timestamped build number."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

BUILD_NUMBER = datetime.now().strftime("%Y%m%d-%H%M")

Path(__file__).resolve().parent.joinpath("build_info.py").write_text(
    '"""Build metadata — overwritten by build_exe.bat on each release build."""\n\n'
    f'BUILD_NUMBER = "{BUILD_NUMBER}"\n',
    encoding="utf-8",
)
print(f"Build number: {BUILD_NUMBER}")
