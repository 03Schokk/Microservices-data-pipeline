"""
lab1_service - main.py (Updated for your ER-diagram and Lab #1 requirements)
"""
from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Optional
from datetime import date
import search  # Предполагаем, что логика запросов здесь
from auth import verify_service_token

app = FastAPI(title="Lab1 Service - Attendance & Search")

# Модели данных на основе ТВОЕЙ ER-диаграммы
class UniversityInfo(BaseModel):
    name: str
    address: str
    founded_year: int # Добавили из твоей схемы

class StudentReport(BaseModel):
    last_name: str
    first_name: str
    patronymic: Optional[str] = None
    email: str
    group_name: str
    # По заданию: данные о занятии, которое прогуляли
    missed_lecture_title: str 
    lecture_type: str # Лекция/Практика из твоей схемы
    # Статистика
    attendance_note: str # "Отсутствовал"
    university: Optional[UniversityInfo] = None

class ReportResponse(BaseModel):
    term: str
    found_students_count: int
    students: List[StudentReport]

@app.post("/report", response_model=ReportResponse)
async def report(term: str, start_date: str, end_date: str, _ = Depends(verify_service_token)):
    try:
        start = date.fromisoformat(start_date)
        end = date.fromisoformat(end_date)
        
        # 1. Идем в ElasticSearch (как в твоей схеме распределения)
        # Ищем ID лекций, которые содержат 'term' в названии или аннотации
        lecture_ids = await search.find_lectures_by_term_in_es(term)
        
        if not lecture_ids:
            return ReportResponse(term=term, found_students_count=0, students=[])

        # 2. Идем в PostgreSQL (таблица attendance)
        # Ищем студентов, которые были 'Отсутствовал' на этих лекциях в период start/end
        # ВАЖНО: учитываем партиционирование по week_start_date
        data = search.get_absent_students_from_pg(lecture_ids, start, end)
        
        # 3. Добавляем данные об иерархии (из MongoDB, согласно твоей схеме)
        # Твоя схема распределения: MongoDB хранит иерархию University-Institute-Department
        enriched_data = await search.enrich_with_university_info(data)

        return ReportResponse(
            term=term,
            found_students_count=len(enriched_data),
            students=enriched_data[:10] # По заданию нужно 10 студентов
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid date format")
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
