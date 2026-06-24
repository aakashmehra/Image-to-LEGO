"""
Product storage and management utilities.
Uses JSON file for simple data persistence.
"""
import json
import os
from typing import List, Dict, Optional
from datetime import datetime
import uuid

PRODUCTS_FILE = os.path.join(os.path.dirname(__file__), "data", "products.json")
PRODUCT_IMAGES_DIR = os.path.join(os.path.dirname(__file__), "static", "images", "products")

def ensure_directories():
    """Ensure required directories exist."""
    os.makedirs(os.path.dirname(PRODUCTS_FILE), exist_ok=True)
    os.makedirs(PRODUCT_IMAGES_DIR, exist_ok=True)


def load_products() -> List[Dict]:
    """Load all products from JSON file."""
    ensure_directories()
    if not os.path.exists(PRODUCTS_FILE):
        return []
    try:
        with open(PRODUCTS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return []


def save_products(products: List[Dict]):
    """Save products to JSON file."""
    ensure_directories()
    with open(PRODUCTS_FILE, 'w', encoding='utf-8') as f:
        json.dump(products, f, indent=2, ensure_ascii=False)


def get_product(product_id: str) -> Optional[Dict]:
    """Get a single product by ID."""
    products = load_products()
    for product in products:
        if product.get('id') == product_id:
            return product
    return None


def create_product(product_data: Dict) -> Dict:
    """Create a new product."""
    products = load_products()
    
    # Generate ID and slug
    product_id = product_data.get('id') or str(uuid.uuid4())
    title = product_data.get('title', 'Untitled Product')
    slug = product_data.get('slug') or title.lower().replace(' ', '-').replace('/', '-')[:50]
    
    # Ensure unique slug
    existing_slugs = [p.get('slug', '') for p in products]
    original_slug = slug
    counter = 1
    while slug in existing_slugs:
        slug = f"{original_slug}-{counter}"
        counter += 1
    
    new_product = {
        'id': product_id,
        'slug': slug,
        'title': product_data.get('title', 'Untitled Product'),
        'short_description': product_data.get('short_description', ''),
        'description': product_data.get('description', ''),
        'price': int(product_data.get('price', 0)),  # in cents
        'compare_at_price': int(product_data.get('compare_at_price', 0)),
        'currency': product_data.get('currency', 'USD'),
        'status': product_data.get('status', 'draft'),  # published, draft, archived
        'sku': product_data.get('sku', ''),
        'inventory': int(product_data.get('inventory', 0)),
        'inventory_policy': product_data.get('inventory_policy', 'continue'),  # continue or deny
        'images': product_data.get('images', []),
        'tags': product_data.get('tags', []),
        'categories': product_data.get('categories', []),
        'variants': product_data.get('variants', []),
        'weight': float(product_data.get('weight', 0)),
        'dimensions': product_data.get('dimensions', {}),
        'created_at': datetime.now().isoformat(),
        'updated_at': datetime.now().isoformat(),
    }
    
    products.append(new_product)
    save_products(products)
    return new_product


def update_product(product_id: str, product_data: Dict) -> Optional[Dict]:
    """Update an existing product."""
    products = load_products()
    
    for i, product in enumerate(products):
        if product.get('id') == product_id:
            # Update fields
            for key, value in product_data.items():
                if key not in ('id', 'created_at'):  # Don't update these
                    if key in ('price', 'compare_at_price', 'inventory'):
                        products[i][key] = int(value) if value else 0
                    elif key == 'weight':
                        products[i][key] = float(value) if value else 0.0
                    else:
                        products[i][key] = value
            
            # Ensure slug is unique (if changed)
            if 'slug' in product_data and product_data['slug'] != products[i].get('slug'):
                new_slug = product_data['slug']
                existing_slugs = [p.get('slug', '') for p in products if p.get('id') != product_id]
                original_slug = new_slug
                counter = 1
                while new_slug in existing_slugs:
                    new_slug = f"{original_slug}-{counter}"
                    counter += 1
                products[i]['slug'] = new_slug
            
            products[i]['updated_at'] = datetime.now().isoformat()
            save_products(products)
            return products[i]
    
    return None


def delete_product(product_id: str) -> bool:
    """Delete a product by ID."""
    products = load_products()
    original_count = len(products)
    products = [p for p in products if p.get('id') != product_id]
    
    if len(products) < original_count:
        save_products(products)
        return True
    return False


def get_published_products() -> List[Dict]:
    """Get all published products for public display."""
    products = load_products()
    return [p for p in products if p.get('status') == 'published']


def format_price(price_cents: int, currency: str = 'USD') -> str:
    """Format price in cents to currency string."""
    if currency == 'USD':
        return f"${price_cents / 100:.2f}"
    return f"{price_cents / 100:.2f} {currency}"

