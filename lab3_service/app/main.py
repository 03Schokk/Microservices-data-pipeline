"""
lab3_service - main.py
"""

from fastapi import FastAPI, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import generator
import search
from auth import verify_service_token

app = FastAPI(title="Lab3 Service")

class GenerationResponse(BaseModel):
    status: str
    students: int
    lectures: int
    student_groups: int
    lecture_courses: int
    lecture_materials: int
    schedules: int
    attendance: int
    institutes: int
    departments: int
    specialties: int
    department_specialties: int

class CourseHours(BaseModel):
    course_name: str
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

@app.post("/generate", response_model=GenerationResponse)
async def generate(_ = Depends(verify_service_token)):
    try:
        result = generator.run_generation()
        return GenerationResponse(**result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/report", response_model=ReportResponse)
async def report(group_name: str, _ = Depends(verify_service_token)):
    try:
        data = search.generate_report(group_name)
        return ReportResponse(**data)
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))