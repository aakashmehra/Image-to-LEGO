"""
Coupon storage and management utilities.
Uses JSON file for simple data persistence.
"""
import json
import os
from typing import List, Dict, Optional
from datetime import datetime
import uuid

COUPONS_FILE = os.path.join(os.path.dirname(__file__), "data", "coupons.json")

def ensure_directories():
    """Ensure required directories exist."""
    os.makedirs(os.path.dirname(COUPONS_FILE), exist_ok=True)


def load_coupons() -> List[Dict]:
    """Load all coupons from JSON file."""
    ensure_directories()
    if not os.path.exists(COUPONS_FILE):
        return []
    try:
        with open(COUPONS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return []


def save_coupons(coupons: List[Dict]):
    """Save coupons to JSON file."""
    ensure_directories()
    with open(COUPONS_FILE, 'w', encoding='utf-8') as f:
        json.dump(coupons, f, indent=2, ensure_ascii=False)


def get_coupon(coupon_id: str) -> Optional[Dict]:
    """Get a single coupon by ID."""
    coupons = load_coupons()
    for coupon in coupons:
        if coupon.get('id') == coupon_id:
            return coupon
    return None


def get_coupon_by_code(code: str) -> Optional[Dict]:
    """Get a coupon by its code."""
    coupons = load_coupons()
    for coupon in coupons:
        if coupon.get('code', '').upper() == code.upper():
            return coupon
    return None


def create_coupon(coupon_data: Dict) -> Dict:
    """Create a new coupon."""
    coupons = load_coupons()
    
    # Generate ID
    coupon_id = coupon_data.get('id') or str(uuid.uuid4())
    
    new_coupon = {
        'id': coupon_id,
        'code': coupon_data.get('code', '').upper().strip(),
        'description': coupon_data.get('description', ''),
        'discount_type': coupon_data.get('discount_type', 'percentage'),  # percentage or fixed
        'discount_value': float(coupon_data.get('discount_value', 0)),  # percentage or cents
        'minimum_amount': int(coupon_data.get('minimum_amount', 0)),  # minimum order amount in cents
        'maximum_discount': int(coupon_data.get('maximum_discount', 0)),  # max discount in cents (for percentage)
        'usage_limit': int(coupon_data.get('usage_limit', 0)),  # 0 = unlimited
        'used_count': 0,
        'status': coupon_data.get('status', 'active'),  # active, inactive, expired
        'valid_from': coupon_data.get('valid_from', datetime.now().isoformat()),
        'valid_until': coupon_data.get('valid_until', ''),
        'created_at': datetime.now().isoformat(),
        'updated_at': datetime.now().isoformat(),
    }
    
    coupons.append(new_coupon)
    save_coupons(coupons)
    return new_coupon


def update_coupon(coupon_id: str, coupon_data: Dict) -> Optional[Dict]:
    """Update an existing coupon."""
    coupons = load_coupons()
    
    for i, coupon in enumerate(coupons):
        if coupon.get('id') == coupon_id:
            # Update fields
            for key, value in coupon_data.items():
                if key not in ('id', 'created_at', 'used_count'):  # Don't update these
                    if key in ('minimum_amount', 'maximum_discount', 'usage_limit'):
                        coupons[i][key] = int(value) if value else 0
                    elif key == 'discount_value':
                        coupons[i][key] = float(value) if value else 0.0
                    elif key == 'code':
                        coupons[i][key] = str(value).upper().strip()
                    else:
                        coupons[i][key] = value
            
            coupons[i]['updated_at'] = datetime.now().isoformat()
            save_coupons(coupons)
            return coupons[i]
    
    return None


def delete_coupon(coupon_id: str) -> bool:
    """Delete a coupon by ID."""
    coupons = load_coupons()
    original_count = len(coupons)
    coupons = [c for c in coupons if c.get('id') != coupon_id]
    
    if len(coupons) < original_count:
        save_coupons(coupons)
        return True
    return False


def increment_coupon_usage(coupon_id: str) -> bool:
    """Increment the usage count for a coupon."""
    coupons = load_coupons()
    
    for i, coupon in enumerate(coupons):
        if coupon.get('id') == coupon_id:
            coupons[i]['used_count'] = coupons[i].get('used_count', 0) + 1
            save_coupons(coupons)
            return True
    
    return False


def validate_coupon(coupon: Dict, order_amount: int = 0) -> tuple[bool, str]:
    """Validate if a coupon can be used. Returns (is_valid, error_message)."""
    if coupon.get('status') != 'active':
        return False, "Coupon is not active"
    
    # Check expiration
    valid_until = coupon.get('valid_until')
    if valid_until:
        try:
            from datetime import datetime
            if datetime.fromisoformat(valid_until) < datetime.now():
                return False, "Coupon has expired"
        except:
            pass
    
    # Check usage limit
    usage_limit = coupon.get('usage_limit', 0)
    if usage_limit > 0 and coupon.get('used_count', 0) >= usage_limit:
        return False, "Coupon usage limit reached"
    
    # Check minimum amount
    minimum_amount = coupon.get('minimum_amount', 0)
    if minimum_amount > 0 and order_amount < minimum_amount:
        return False, f"Minimum order amount of ${minimum_amount / 100:.2f} required"
    
    return True, ""

