from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.session import get_db
from app.models.database import ValidationAssessment
from app.models.schemas import ValidationAssessmentCreate, ValidationAssessmentOut
from typing import List, Optional
import uuid
from datetime import datetime

router = APIRouter(prefix="/validation", tags=["validation"])


@router.post("/assessments", response_model=ValidationAssessmentOut)
async def create_assessment(
    payload: ValidationAssessmentCreate,
    db: AsyncSession = Depends(get_db)
):
    record = ValidationAssessment(
        assessment_id=str(uuid.uuid4()),
        **payload.dict()
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)
    return record


@router.get("/assessments", response_model=List[ValidationAssessmentOut])
async def get_assessments(
    jira_ticket: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    query = select(ValidationAssessment).order_by(
        ValidationAssessment.assessment_date.desc()
    )
    if jira_ticket:
        query = query.where(ValidationAssessment.jira_ticket == jira_ticket)
    result = await db.execute(query)
    return result.scalars().all()
