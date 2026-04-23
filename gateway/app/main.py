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

LAB1_SERVICE_URL = "https://lab1-nginx:443"   # имя контейнера в docker-compose

# получает JWT для сервиса lab1-service через грант client_credentials. Этот токен будет передан в lab1_service для авторизации
async def get_service_token():
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "http://localhost:8000/token",  # внутренний вызов самого себя
            data={
                "grant_type": "client_credentials",
                "client_id": "lab1-service",
                "client_secret": "lab1-secret"
            }
        )
        resp.raise_for_status()
        return resp.json()["access_token"]

# эндпоинт выдачи токенов
# 2 типа:
# - grant_type=password - для пользователей (username/password). Возвращает токен с "type": "user"
# - grant_type=client_credentials — для сервисов (client_id/client_secret). Возвращает токен с "type": "service" и списком scopes
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

# Прокси-запрос к генератору lab1: получение собственного токена -> отправка запрос через mTLS-клиент. Пользователь должен быть аутентифицирован
@app.post("/api/lab1/generate")
async def generate_data(current_user: User = Depends(get_current_active_user)):
    """Запуск генерации тестовых данных во все БД"""
    token = await get_service_token()
    headers = {"Authorization": f"Bearer {token}"}
    async with get_mtls_client() as client:
        try:
            resp = await client.post(f"{LAB1_SERVICE_URL}/generate", headers=headers, timeout=300.0)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as e:
            raise HTTPException(status_code=502, detail=f"Lab1 service error: {str(e)}")

# Прокси-запрос к поиску данных lab1: получение собственного токена -> отправка запрос через mTLS-клиент. Пользователь должен быть аутентифицирован
@app.post("/api/lab1/report")
async def get_report(
    term: str,
    start_date: str,
    end_date: str,
    current_user: User = Depends(get_current_active_user)
):
    """Получение отчёта по лабораторной работе №1"""
    token = await get_service_token()
    headers = {"Authorization": f"Bearer {token}"}
    async with get_mtls_client() as client:
        try:
            resp = await client.post(
                f"{LAB1_SERVICE_URL}/report",
                headers=headers,
                params={"term": term, "start_date": start_date, "end_date": end_date},
                timeout=60.0
            )
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as e:
            raise HTTPException(status_code=502, detail=f"Lab1 service error: {str(e)}")