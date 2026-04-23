"""
gateway - auth.py 
"""

from datetime import datetime, timedelta, timezone
from typing import Optional
from jose import JWTError, jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel
import bcrypt

# Конфигурация JWT
SECRET_KEY = "secret-key"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))

users_db = {
    "admin": {
        "username": "admin",
        "full_name": "Admin User",
        "email": "admin@example.com",
        "hashed_password": hash_password("secret"),   # хэшируем при старте
        "disabled": False,
    }
}

clients_db = {
    "lab1-service": {
        "client_id": "lab1-service",
        "client_secret": hash_password("lab1-secret"),
        "scopes": ["lab1:generate", "lab1:report"]
    }
}

# модель ответа при получении токена
class Token(BaseModel): 
    access_token: str
    token_type: str

# данные, извлечённые из JWT
class TokenData(BaseModel): 
    username: Optional[str] = None

# модель пользователя
class User(BaseModel): 
    username: str
    email: Optional[str] = None
    full_name: Optional[str] = None
    disabled: Optional[bool] = None

class UserInDB(User):
    hashed_password: str

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token") # для получения токена нужно отправить запрос на /token с параметрами username, password

# поиск пользователя в БД
def get_user(db, username: str):
    if username in db:
        user_dict = db[username]
        return UserInDB(**user_dict)

# проверка пароля при логине
def authenticate_user(fake_db, username: str, password: str):
    user = get_user(fake_db, username)
    if not user:
        return False
    if not verify_password(password, user.hashed_password):
        return False
    return user

# Создание JWT. В data кладётся sub (идентификатор субъекта) и type (user/service). Время жизни указывается в exp.
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

# декодирует JWT, проверяет подпись и извлекает пользователя. Если токен невалиден — возвращает 401
async def get_current_user(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
        token_data = TokenData(username=username)
    except JWTError as e:
        # Добавим вывод ошибки в логи для диагностики
        print(f"JWT decode error: {e}")
        raise credentials_exception
    user = get_user(users_db, username=token_data.username)
    if user is None:
        raise credentials_exception
    return user

# проверяет, что пользователь не заблокирован
async def get_current_active_user(current_user: User = Depends(get_current_user)):
    if current_user.disabled:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user

# аутентификация OAuth-клиента (сервиса) по client_id и client_secret.
def authenticate_client(client_id: str, client_secret: str):
    client = clients_db.get(client_id)
    if not client:
        return False
    if not verify_password(client_secret, client["client_secret"]):
        return False
    return client