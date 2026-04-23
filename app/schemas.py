from pydantic import BaseModel
from datetime import datetime

class JournalEntryCreate(BaseModel):
    title: str
    content: str

class JournalEntryResponse(BaseModel):
    id: int
    user_id: int
    title: str
    content: str
    created_at: datetime
    class Config:
        from_attributes = True
