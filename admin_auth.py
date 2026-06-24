import os
import hashlib
import secrets

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ADMIN_PASSWORD_FILE = os.path.join(BASE_DIR, "data", "admin_password.txt")


def ensure_data_dir():
    """Ensure data directory exists"""
    data_dir = os.path.join(BASE_DIR, "data")
    os.makedirs(data_dir, exist_ok=True)


def hash_password(password: str) -> str:
    """Hash a password using SHA256"""
    return hashlib.sha256(password.encode()).hexdigest()


def save_admin_password(password: str) -> str:
    """Save admin password and return the hashed version"""
    ensure_data_dir()
    hashed = hash_password(password)
    with open(ADMIN_PASSWORD_FILE, 'w') as f:
        f.write(hashed)
    return hashed


def get_admin_password_hash() -> str | None:
    """Get the stored admin password hash"""
    if not os.path.exists(ADMIN_PASSWORD_FILE):
        return None
    try:
        with open(ADMIN_PASSWORD_FILE, 'r') as f:
            return f.read().strip()
    except:
        return None


def verify_password(password: str) -> bool:
    """Verify if password matches stored hash"""
    stored_hash = get_admin_password_hash()
    if not stored_hash:
        return False
    return hash_password(password) == stored_hash


def admin_password_exists() -> bool:
    """Check if admin password has been set"""
    return os.path.exists(ADMIN_PASSWORD_FILE) and get_admin_password_hash() is not None

