"""Owner list reads.

A sorted Mongo find can follow an index and leave out documents that are not
in that index. The route then returns 200 and an empty list. These reads pin
the primary as well, so a secondary readPreference on MONGO_URL cannot hide a
write the primary already accepted. Order the rows in process. Do not log the
documents: invite tokens and register URLs must stay out of the logs.
"""
from pymongo import ReadPreference

# The raw invite token is not an owner-list field. register_url still carries
# it, because that URL is the link the owner copies.
_INVITE_OMIT = frozenset({"_id", "token"})


def public_invite(invite: dict) -> dict:
    """Invite fields safe to return to the signed-in owner."""
    if not invite:
        return {}
    return {key: value for key, value in invite.items() if key not in _INVITE_OMIT}


async def owner_documents(collection, query=None, limit=200, sort_key=None, reverse=False):
    """Load owner-facing documents with no server-side sort.

    `sort()` is intentionally not called on the cursor. A sorted find is what
    emptied the shop-request list.
    """
    target = collection
    with_options = getattr(collection, "with_options", None)
    if callable(with_options):
        target = with_options(read_preference=ReadPreference.PRIMARY)
    cursor = target.find({} if query is None else query, {"_id": 0})
    docs = await cursor.to_list(int(limit))
    if docs is None:
        docs = []
    if sort_key:
        docs.sort(key=lambda row: str((row or {}).get(sort_key) or ""), reverse=reverse)
    return docs
