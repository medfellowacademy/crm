"""
Authentication and Authorization Module
Provides JWT token generation, password hashing, and user verification
"""

from datetime import datetime, timedelta
from typing import Optional
import os
from jose import JWTError, jwt
import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from pydantic import BaseModel

# Security configuration
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "your-secret-key-change-in-production-use-openssl-rand-hex-32")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "1440"))  # 24 hours

# OAuth2 scheme
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


class Token(BaseModel):
    access_token: str
    token_type: str
    user: dict


class TokenData(BaseModel):
    email: Optional[str] = None
    role: Optional[str] = None


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain password against a hashed password"""
    try:
        password_bytes = plain_password.encode('utf-8')[:72]
        hashed_bytes = hashed_password.encode('utf-8')
        return bcrypt.checkpw(password_bytes, hashed_bytes)
    except Exception:
        return False


def get_password_hash(password: str) -> str:
    """Hash a password using bcrypt"""
    password_bytes = password.encode('utf-8')[:72]  # Bcrypt 72 byte limit
    return bcrypt.hashpw(password_bytes, bcrypt.gensalt()).decode('utf-8')


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a JWT access token"""
    to_encode = data.copy()
    
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    
    return encoded_jwt


def decode_access_token(token: str) -> TokenData:
    """Decode and verify a JWT token"""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        role: str = payload.get("role")
        
        if email is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        return TokenData(email=email, role=role)
    
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )


def authenticate_user(db: Session, email: str, password: str):
    """Authenticate a user by email and password"""
    from main import DBUser  # Import here to avoid circular dependency
    
    user = db.query(DBUser).filter(DBUser.email == email).first()
    
    if not user:
        return False
    
    if not verify_password(password, user.password):
        return False
    
    return user


def get_db_dependency():
    """Get database session - imported here to avoid circular dependency"""
    from main import get_db
    return get_db


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db_dependency)
):
    """Get the current authenticated user from JWT token"""
    from main import DBUser  # Import here to avoid circular dependency
    
    token_data = decode_access_token(token)
    
    user = db.query(DBUser).filter(DBUser.email == token_data.email).first()
    
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return user


def require_role(allowed_roles: list):
    """Decorator to require specific roles for endpoint access"""
    async def role_checker(current_user = Depends(get_current_user)):
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Required roles: {', '.join(allowed_roles)}"
            )
        return current_user
    
    return role_checker


# Role-based access helpers
async def get_current_counselor(current_user = Depends(get_current_user)):
    """Require Counselor role or higher"""
    if current_user.role not in ["Counselor", "Team Leader", "Manager", "Super Admin"]:
        raise HTTPException(status_code=403, detail="Counselor access required")
    return current_user


async def get_current_team_leader(current_user = Depends(get_current_user)):
    """Require Team Leader role or higher"""
    if current_user.role not in ["Team Leader", "Manager", "Super Admin"]:
        raise HTTPException(status_code=403, detail="Team Leader access required")
    return current_user


async def get_current_manager(current_user = Depends(get_current_user)):
    """Require Manager role or higher"""
    if current_user.role not in ["Manager", "Super Admin"]:
        raise HTTPException(status_code=403, detail="Manager access required")
    return current_user


async def get_current_admin(current_user = Depends(get_current_user)):
    """Require Super Admin role"""
    if current_user.role != "Super Admin":
        raise HTTPException(status_code=403, detail="Super Admin access required")
    return current_user
