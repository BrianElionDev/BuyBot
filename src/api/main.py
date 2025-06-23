from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .discord_endpoint import router as discord_router

app = FastAPI(title="Trading Bot API")

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(discord_router, prefix="/api/v1", tags=["discord"])

@app.get("/")
async def root():
    """Root endpoint."""
    return {"message": "Trading Bot API is running"}