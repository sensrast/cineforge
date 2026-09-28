from __future__ import annotations

class JobCancelled(Exception):
    """Raised when the owner cancels an active queue item."""

async def checkpoint(ctx,qid:int)->None:
    row=await ctx.db.db.fetchone("SELECT status FROM queue WHERE id=?",(qid,))
    if row and row["status"]=="cancelled":
        raise JobCancelled(f"Job #{qid} cancelled by owner")
