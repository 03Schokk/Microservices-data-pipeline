"""
lab2_service - auth.py
"""

from jose import JWTError, jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

security = HTTPBearer()

SECRET_KEY = "secret-key" 
ALGORITHM = "HS256"

async def verify_service_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        sub = payload.get("sub")
        token_type = payload.get("type")
        if sub != "lab2-service" or token_type != "service":
            raise HTTPException(status_code=403, detail="Invalid service token")
        return payload
    except JWTError:
        raise HTTPException(status_code=403, detail="Invalid token")