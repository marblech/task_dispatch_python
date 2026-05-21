import hashlib
import os
import base64


class PasswordHelper:
    """密码加密工具类，使用SHA256 + salt方式进行加密"""
    
    SALT_LENGTH = 16

    @staticmethod
    def _sha256_hex(raw_value: str) -> str:
        return hashlib.sha256(raw_value.encode('utf-8')).hexdigest()
    
    @staticmethod
    def generate_salt() -> str:
        """生成随机salt"""
        salt = os.urandom(PasswordHelper.SALT_LENGTH)
        return base64.b64encode(salt).decode('utf-8')
    
    @staticmethod
    def hash_password(password: str, salt: str = None) -> tuple:
        """
        对密码进行加密
        Args:
            password: 明文密码
            salt: salt，如果不提供则自动生成
        Returns:
            (hashed_password, salt) 元组
        """
        if salt is None:
            salt = PasswordHelper.generate_salt()
        
        # 使用SHA256对密码和salt进行哈希
        password_hash = PasswordHelper._sha256_hex(password + salt)
        return password_hash, salt
    
    @staticmethod
    def verify_password(password: str, hashed_password: str, salt: str) -> bool:
        """
        验证密码
        Args:
            password: 明文密码
            hashed_password: 存储的哈希密码
            salt: 加密时使用的salt
        Returns:
            bool: 密码是否匹配
        """
        if not hashed_password:
            return False

        if salt:
            password_hash, _ = PasswordHelper.hash_password(password, salt)
            return password_hash == hashed_password

        legacy_hash = PasswordHelper._sha256_hex(password)
        return hashed_password in {legacy_hash, password}

    @staticmethod
    def password_needs_upgrade(salt: str | None) -> bool:
        return not salt
    
    @staticmethod
    def create_default_admin() -> dict:
        """
        创建默认管理员账号
        Returns:
            dict: 包含username, user_pwd(哈希后), salt的信息
        """
        username = "admin"
        password = "admin123"  # 默认密码，用户可以后续修改
        
        hashed_pwd, salt = PasswordHelper.hash_password(password)
        
        return {
            "username": username,
            "user_pwd": hashed_pwd,
            "salt": salt
        }