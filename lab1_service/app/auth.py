"""
lab1_service - auth.py
"""

from jose import JWTError, jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

security = HTTPBearer() # схема, которая ожидает заголовок Authorization: Bearer <token>

# те же самые секрет и алгоритм, что и в gateway 
# (необходимы для того, чтобы сервис мог верифицировать JWT, выданный gateway)
SECRET_KEY = "secret-key" 
ALGORITHM = "HS256"

# Проверка сервисного токена, которая используется в каждом эндпоинте контейнера lab1
async def verify_service_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials # извлечение токена из заголовка запроса
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM]) # декодирование подписи
        sub = payload.get("sub")
        token_type = payload.get("type")

        # проверка частей токена на верные значения
        # (это гарантирует, что запрос пришёл от доверенного gateway, ведь только он знает client_secret и может получить токен)
        if sub != "lab1-service" or token_type != "service": 
            raise HTTPException(status_code=403, detail="Invalid service token")
            
        return payload
    except JWTError:
        raise HTTPException(status_code=403, detail="Invalid token")