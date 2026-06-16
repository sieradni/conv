"""FastAPI Server - Phase 1 Initialization"""

from fastapi import FastAPI

app = FastAPI(
    title="Agentic Development Framework",
    description="Phase 1: Environment Setup",
    version="0.1.0"
)

@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
