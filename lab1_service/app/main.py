"""
lab1_service - main.py
"""

from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import List, Optional
import generator
import search
from datetime import date
from auth import verify_service_token

app = FastAPI(title="Lab1 Service")

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

class UniversityInfo(BaseModel):
    name: str
    address: str
    website: str

class StudentReport(BaseModel):
    last_name: str
    first_name: str
    patronymic: str
    student_card_number: str
    email: str
    phone: str
    group_name: str
    specialty_name: str
    total_scheduled: int
    attendance_percent: float
    university: Optional[UniversityInfo] = None

class ReportResponse(BaseModel):
    students: List[StudentReport]

# эндпоинт запуска генерации данных (защищён через verify_service_token)
@app.post("/generate", response_model=GenerationResponse)
async def generate(_ = Depends(verify_service_token)):
    try:
        result = generator.run_generation()
        return GenerationResponse(**result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# эндпоинт запуска поиска данных (защищён через verify_service_token)
@app.post("/report", response_model=ReportResponse)
async def report(term: str, start_date: str, end_date: str, _ = Depends(verify_service_token)):
    try:
        start = date.fromisoformat(start_date)
        end = date.fromisoformat(end_date)
        if start > end:
            raise ValueError("start_date must be <= end_date")
        
        pg_conn = search.get_postgres_connection()
        min_db, max_db = search.get_min_max_schedule_dates(pg_conn)
        pg_conn.close()
        if min_db is None or max_db is None:
            raise HTTPException(status_code=404, detail="No schedule data")
        
        # Приводим даты к границам имеющихся данных
        start_adj = max(start, min_db)
        end_adj = min(end, max_db)

        data = search.generate_report(term, start_adj.isoformat(), end_adj.isoformat())
        if not data:
            return ReportResponse(students=[])
        return ReportResponse(students=data)
    except ValueError as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))