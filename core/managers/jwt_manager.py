from datetime import datetime, timedelta
import jwt
from typing import Dict, Any, Optional, Union
from tools.logger.custom_logging import custom_log
from utils.config.config import Config
from core.managers.redis_manager import RedisManager
from enum import Enum

class TokenType(Enum):
    ACCESS = "access"
    REFRESH = "refresh"
    WEBSOCKET = "websocket"

class JWTManager:
    def __init__(self):
        self.redis_manager = RedisManager()
        self.secret_key = Config.JWT_SECRET_KEY
        self.algorithm = Config.JWT_ALGORITHM
        self.access_token_expire_seconds = Config.JWT_ACCESS_TOKEN_EXPIRES
        self.refresh_token_expire_seconds = Config.JWT_REFRESH_TOKEN_EXPIRES
        custom_log("JWTManager initialized")

    def create_token(self, data: Dict[str, Any], token_type: TokenType, expires_in: Optional[int] = None) -> str:
        """Create a new JWT token of specified type."""
        to_encode = data.copy()
        
        # Set expiration based on token type
        if expires_in:
            expire = datetime.utcnow() + timedelta(seconds=expires_in)
        else:
            if token_type == TokenType.ACCESS:
                expire = datetime.utcnow() + timedelta(seconds=self.access_token_expire_seconds)
            elif token_type == TokenType.REFRESH:
                expire = datetime.utcnow() + timedelta(seconds=self.refresh_token_expire_seconds)
            else:  # WEBSOCKET
                expire = datetime.utcnow() + timedelta(seconds=self.access_token_expire_seconds)
            
        to_encode.update({
            "exp": expire,
            "type": token_type.value,
            "iat": datetime.utcnow()
        })
        
        encoded_jwt = jwt.encode(to_encode, self.secret_key, algorithm=self.algorithm)
        
        # Store token in Redis for revocation capability
        self._store_token(encoded_jwt, expire, token_type)
        
        return encoded_jwt

    def verify_token(self, token: str, expected_type: Optional[TokenType] = None) -> Optional[Dict[str, Any]]:
        """Verify a JWT token and return its payload if valid."""
        try:
            # Check if token is revoked
            if self._is_token_revoked(token):
                custom_log(f"Token revoked: {token[:10]}...")
                return None
                
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
            
            # Verify token type if specified
            if expected_type and payload.get("type") != expected_type.value:
                custom_log(f"Invalid token type. Expected: {expected_type.value}, Got: {payload.get('type')}")
                return None
                
            return payload
        except jwt.ExpiredSignatureError:
            custom_log("Token has expired")
            return None
        except jwt.JWTError as e:
            custom_log(f"JWT verification failed: {str(e)}")
            return None

    def revoke_token(self, token: str) -> bool:
        """Revoke a JWT token."""
        try:
            # Store revoked token in Redis with its expiration time
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
            exp_timestamp = payload.get("exp")
            if exp_timestamp:
                # Store until token expires
                ttl = exp_timestamp - int(datetime.utcnow().timestamp())
                if ttl > 0:
                    self.redis_manager.set(f"jwt:revoked:{token}", "1", expire=ttl)
                    custom_log(f"Token revoked: {token[:10]}...")
                    return True
            return False
        except jwt.JWTError:
            return False

    def refresh_token(self, refresh_token: str) -> Optional[str]:
        """Create a new access token using a refresh token."""
        payload = self.verify_token(refresh_token, TokenType.REFRESH)
        if payload:
            # Remove refresh-specific claims
            new_payload = {k: v for k, v in payload.items() 
                         if k not in ['exp', 'iat', 'type']}
            return self.create_token(new_payload, TokenType.ACCESS)
        return None

    def _store_token(self, token: str, expire: datetime, token_type: TokenType):
        """Store token in Redis for tracking."""
        ttl = int(expire.timestamp() - datetime.utcnow().timestamp())
        if ttl > 0:
            self.redis_manager.set(f"jwt:active:{token_type.value}:{token}", "1", expire=ttl)

    def _is_token_revoked(self, token: str) -> bool:
        """Check if a token is revoked."""
        return bool(self.redis_manager.get(f"jwt:revoked:{token}"))

    def cleanup_expired_tokens(self):
        """Clean up expired tokens from Redis."""
        # This can be called periodically to clean up expired tokens
        # Implementation depends on your Redis key pattern
        pass

    # Convenience methods for specific use cases
    def create_access_token(self, data: Dict[str, Any], expires_in: Optional[int] = None) -> str:
        """Create a new access token."""
        return self.create_token(data, TokenType.ACCESS, expires_in)

    def create_refresh_token(self, data: Dict[str, Any], expires_in: Optional[int] = None) -> str:
        """Create a new refresh token."""
        return self.create_token(data, TokenType.REFRESH, expires_in)

    def create_websocket_token(self, data: Dict[str, Any], expires_in: Optional[int] = None) -> str:
        """Create a new WebSocket token."""
        return self.create_token(data, TokenType.WEBSOCKET, expires_in)

    def verify_websocket_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Verify a WebSocket token."""
        return self.verify_token(token, TokenType.WEBSOCKET) 