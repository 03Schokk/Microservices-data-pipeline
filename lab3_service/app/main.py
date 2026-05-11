"""
lab3_service - main.py
"""

from fastapi import FastAPI, Depends, HTTPException
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import search
from auth import verify_service_token

app = FastAPI(title="Lab3 Service")

class CourseHours(BaseModel):
    course_name: str
    semester: int
    planned_hours: int
    attended_hours: int

class StudentReport(BaseModel):
    last_name: str
    first_name: str
    patronymic: str
    student_card_number: str
    email: str
    phone: str
    courses: List[CourseHours]

class ReportResponse(BaseModel):
    group_name: str
    university: Optional[Dict[str, Any]] = None
    students: List[StudentReport]

@app.post("/report", response_model=ReportResponse)
async def report(group_name: str, _ = Depends(verify_service_token)):
    try:
        data = search.generate_report(group_name)
        return ReportResponse(**data)
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))