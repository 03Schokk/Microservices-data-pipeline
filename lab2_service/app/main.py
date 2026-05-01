"""
lab2_service - main.py
"""

from fastapi import FastAPI, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import List
import generator
import search
from auth import verify_service_token

app = FastAPI(title="Lab2 Service")

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

class LectureReport(BaseModel):
    specialty_name: str
    course_name: str
    course_description: str
    semester: int
    lecture_title: str
    lecture_type: str
    computer_type: str
    student_count: int

class ReportResponse(BaseModel):
    lectures: List[LectureReport]

@app.post("/generate", response_model=GenerationResponse)
async def generate(_ = Depends(verify_service_token)):
    try:
        result = generator.run_generation()
        return GenerationResponse(**result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/report", response_model=ReportResponse)
async def report(semester: int, year: int, _ = Depends(verify_service_token)):
    try:
        data = search.generate_report(semester, year)
        return ReportResponse(lectures=data)
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))