from pydantic import BaseModel, Field
from typing import Optional

class InitialDiscordSignal(BaseModel):
    timestamp: str
    content: str
    structured: str

class DiscordUpdateSignal(BaseModel):
    timestamp: str
    content: str
    trade: str = Field(..., description="Reference to original trade signal_id")
    discord_id: str
    trader: Optional[str] = None