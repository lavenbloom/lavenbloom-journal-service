from fastapi import FastAPI, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app import models, schemas, database
from app.auth_middleware import get_current_user

models.Base.metadata.create_all(bind=database.engine)

app = FastAPI(title="Journal Service")

@app.get("/health")
def health_check():
    return {"status": "ok"}

@app.post("/journals", response_model=schemas.JournalEntryResponse)
def create_journal(entry: schemas.JournalEntryCreate, db: Session = Depends(database.get_db), user_id: int = Depends(get_current_user)):
    new_entry = models.JournalEntry(user_id=user_id, title=entry.title, content=entry.content)
    db.add(new_entry)
    db.commit()
    db.refresh(new_entry)
    return new_entry

@app.get("/journals", response_model=list[schemas.JournalEntryResponse])
def get_journals(db: Session = Depends(database.get_db), user_id: int = Depends(get_current_user)):
    return db.query(models.JournalEntry).filter(models.JournalEntry.user_id == user_id).order_by(models.JournalEntry.created_at.desc()).all()
