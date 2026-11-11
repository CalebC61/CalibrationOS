"""Live-server integration tests are skipped unless RUN_INTEGRATION=1 and
REACT_APP_BACKEND_URL points at a running CalibrationOS API."""
import os

INTEGRATION_MODULES = [
    "test_assist.py",
    "test_calibrationos.py",
    "test_growth.py",
    "test_iteration3.py",
    "test_iteration4.py",
]

_enabled = os.environ.get("RUN_INTEGRATION") == "1" and os.environ.get("REACT_APP_BACKEND_URL")
collect_ignore = [] if _enabled else INTEGRATION_MODULES
