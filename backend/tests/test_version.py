"""The changelog's current version and the frontend package version stay the same.

    cd backend && pytest tests/test_version.py -v
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_changelog_top_version_matches_frontend_package():
    package_version = json.loads((ROOT / "frontend" / "package.json").read_text())["version"]
    changelog = (ROOT / "CHANGELOG.md").read_text()
    headings = re.findall(r"^## \[([^\]]+)\]", changelog, re.MULTILINE)
    assert headings, "CHANGELOG.md has no version headings"
    assert headings[0] == package_version
    assert "0.0.3" in headings[1:]
