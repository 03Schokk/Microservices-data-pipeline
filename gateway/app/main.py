"""
gateway - main.py 
"""

from fastapi import FastAPI, Form, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordRequestForm
import httpx
from auth import (
    Token,
    authenticate_user,
    authenticate_client,
    create_access_token,
    get_current_active_user,
    users_db,
    ACCESS_TOKEN_EXPIRE_MINUTES,
    User
)
from datetime import timedelta
from mtls_client import get_mtls_client
from typing import Optional

app = FastAPI(title="API Gateway")

LAB_SERVICE_URL = "https://nginx:443"
LAB1_PATH = "/lab1"
LAB2_PATH = "/lab2"
LAB3_PATH = "/lab3"

# получает JWT для сервиса lab1-service через грант client_credentials. Этот токен будет передан в lab_service для авторизации
async def get_service_token(client_id: str, client_secret: str):
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "http://localhost:8000/token",  # внутренний вызов самого себя
            data={
                "grant_type": "client_credentials",
                "client_id": client_id,
                "client_secret": client_secret
            }
        )
        resp.raise_for_status()
        return resp.json()["access_token"]

# эндпоинт выдачи токенов
# 2 типа:
# - grant_type=password - для пользователей (username/password). Возвращает токен с "type": "user"
# - grant_type=client_credentials - для сервисов (client_id/client_secret). Возвращает токен с "type": "service" и списком scopes
@app.post("/token", response_model=Token)
async def login(
    grant_type: str = Form(...),
    username: Optional[str] = Form(None),
    password: Optional[str] = Form(None),
    client_id: Optional[str] = Form(None),
    client_secret: Optional[str] = Form(None),
):
    if grant_type == "password":
        user = authenticate_user(users_db, username, password)
        if not user:
            raise HTTPException(status_code=400, detail="Incorrect username or password")
        access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(
            data={"sub": user.username, "type": "user"},
            expires_delta=access_token_expires
        )
        return {"access_token": access_token, "token_type": "bearer"}
    elif grant_type == "client_credentials":
        client = authenticate_client(client_id, client_secret)
        if not client:
            raise HTTPException(status_code=400, detail="Invalid client credentials")
        access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(
            data={"sub": client_id, "type": "service", "scopes": client["scopes"]},
            expires_delta=access_token_expires
        )
        return {"access_token": access_token, "token_type": "bearer"}
    else:
        raise HTTPException(status_code=400, detail="Unsupported grant_type")

# защищённый эндпоинт, возвращает информацию о текущем аутентифицированном пользователе
@app.get("/users/me", response_model=User)
async def read_users_me(current_user: User = Depends(get_current_active_user)):
    return current_user

# Прокси-запрос к поиску данных lab1: получение собственного токена -> отправка запрос через mTLS-клиент. Пользователь должен быть аутентифицирован
@app.post("/api/lab1/report")
async def get_report(term: str, start_date: str, end_date: str, current_user: User = Depends(get_current_active_user)):
    """Получение отчёта по лабораторной работе №1"""
    token = await get_service_token("lab1-service", "lab1-secret")
    headers = {"Authorization": f"Bearer {token}"}
    async with get_mtls_client() as client:
        try:
            resp = await client.post(
                f"{LAB_SERVICE_URL}{LAB1_PATH}/report",
                headers=headers,
                params={"term": term, "start_date": start_date, "end_date": end_date},
                timeout=60.0
            )
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as e:
            raise HTTPException(status_code=502, detail=f"Lab1 service error: {str(e)}")

@app.post("/api/lab2/report")
async def get_report(semester: str, year: str, current_user: User = Depends(get_current_active_user)):
    """Получение отчёта по лабораторной работе №2"""
    token = await get_service_token("lab2-service", "lab2-secret")
    headers = {"Authorization": f"Bearer {token}"}
    async with get_mtls_client() as client:
        try:
            resp = await client.post(
                f"{LAB_SERVICE_URL}{LAB2_PATH}/report",
                headers=headers,
                params={"semester": semester, "year": year},
                timeout=60.0
            )
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as e:
            raise HTTPException(status_code=502, detail=f"Lab2 service error: {str(e)}")

@app.post("/api/lab3/report")
async def get_report(group_name: str, current_user: User = Depends(get_current_active_user)):
    """Получение отчёта по лабораторной работе №3"""
    token = await get_service_token("lab3-service", "lab3-secret")
    headers = {"Authorization": f"Bearer {token}"}
    async with get_mtls_client() as client:
        try:
            resp = await client.post(
                f"{LAB_SERVICE_URL}{LAB3_PATH}/report",
                headers=headers,
                params={"group_name": group_name},
                timeout=60.0
            )
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as e:
            raise HTTPException(status_code=502, detail=f"Lab3 service error: {str(e)}")