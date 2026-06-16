"""Sleep Flow — offline memory optimization and graph maintenance.

Runs as a background task to:
1. Promote high-access nodes into parent summaries.
2. Compress/prune stale, low-access leaf nodes.
3. Discover and add lateral small-world links.
4. Reset access counters and update timestamps.
"""

import asyncio
import logging
from app.memory_graph import get_memory_graph

logger = logging.getLogger("sleep_flow")


async def run_sleep_cycle():
    """Execute one full sleep optimization cycle on the memory graph."""
    logger.info("Sleep flow starting...")
    graph = get_memory_graph()
    graph.optimize()
    logger.info("Sleep flow complete.")


async def sleep_loop(interval_seconds: int = 3600):
    """Run the sleep flow periodically every `interval_seconds`."""
    while True:
        await asyncio.sleep(interval_seconds)
        try:
            await run_sleep_cycle()
        except Exception as e:
            logger.error(f"Sleep flow error: {e}")
