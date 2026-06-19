"""Memory graph endpoints."""

import logging
from fastapi import APIRouter

from app.memory_graph import get_memory_graph

logger = logging.getLogger("api.memory")
router = APIRouter(tags=["memory"])


@router.get("/api/memory")
async def get_memory_graph_api():
    graph = get_memory_graph()
    return {
        "current_node_id": graph.current_node_id,
        "nodes": graph.get_all_nodes(),
    }


@router.post("/api/memory/optimize")
async def optimize_memory():
    from app.sleep_flow import run_sleep_cycle
    await run_sleep_cycle()
    return {"status": "optimized"}
