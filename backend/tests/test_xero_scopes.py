"""The Xero connect URL must use granular scopes.

Apps created after 2 March 2026 reject the broad accounting.transactions scope.
    cd backend && pytest tests/test_xero_scopes.py -v
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "ci")

import server  # noqa: E402

EXPECTED = (
    "openid profile email accounting.invoices accounting.contacts "
    "accounting.attachments accounting.settings.read offline_access"
)


def test_connect_scopes_are_granular_and_cover_invoices_only():
    assert server.XERO_SCOPES == EXPECTED
    scopes = server.XERO_SCOPES.split()
    assert "accounting.transactions" not in scopes
    assert "accounting.payments" not in scopes
    assert "accounting.invoices" in scopes
    assert not any(scope.startswith("accounting.reports") for scope in scopes)
    assert not any("journal" in scope for scope in scopes)
