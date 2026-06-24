# Admin Product Management Guide

## Overview

This shop system includes a backend admin interface for managing products. All products are stored in a JSON file (`data/products.json`) for simplicity.

## Accessing the Admin Interface

Navigate to: **`/admin/products`**

Example: `http://localhost:5230/admin/products`

## Features

### Product Management
- **List Products**: View all products in a table with images, titles, prices, inventory, and status
- **Create Product**: Add new products with full details
- **Edit Product**: Update existing products
- **Delete Product**: Remove products (with confirmation)

### Product Fields

1. **Basic Information**
   - Title (required)
   - Slug (auto-generated from title if not provided)
   - Short Description
   - Full Description

2. **Pricing**
   - Price (in cents, e.g., 1999 = $19.99)
   - Compare at Price (for sale pricing, optional)

3. **Inventory**
   - SKU (Stock Keeping Unit)
   - Inventory Quantity
   - Inventory Policy:
     - "Continue" - Allow selling when out of stock
     - "Deny" - Stop selling when out of stock

4. **Status**
   - Draft - Not visible in shop
   - Published - Visible in shop (only these show on `/shop`)
   - Archived - Hidden from shop

5. **Organization**
   - Categories (comma-separated)
   - Tags (comma-separated)

6. **Images**
   - Image URLs (one per line)
   - Format: `images/products/photo.jpg` (relative to `static/` folder)
   - First image is used as primary/thumbnail

## Usage Instructions

### Creating a Product

1. Go to `/admin/products`
2. Click "Add New Product"
3. Fill in the form:
   - **Title**: "LEGO Castle Set"
   - **Price**: `4999` (means $49.99)
   - **Compare at Price**: `5999` (optional, for showing sale)
   - **Status**: Select "Published" to make it visible in shop
   - **Images**: Enter one or more image paths like:
     ```
     images/products/castle.jpg
     images/products/castle-back.jpg
     ```
4. Click "Create Product"

### Editing a Product

1. Go to `/admin/products`
2. Click "Edit" on any product
3. Modify fields as needed
4. Click "Update Product"

### Image Setup

Before adding products, upload product images to:
```
static/images/products/
```

Then reference them in the product form as:
```
images/products/your-image.jpg
```

### Example Product Data

```json
{
  "title": "LEGO Castle Set",
  "price": 4999,
  "compare_at_price": 5999,
  "status": "published",
  "inventory": 10,
  "inventory_policy": "deny",
  "images": ["images/products/castle.jpg"],
  "categories": ["LEGO Sets", "Medieval"],
  "tags": ["castle", "medieval", "exclusive"]
}
```

## Cart Functionality

- Products can be added to cart from product detail pages
- Cart is stored in session (temporary, cleared when browser closes)
- View cart at `/cart`
- Update quantities or remove items from cart
- Cart count shows in navbar

## File Structure

```
data/
  products.json          # Product database (JSON)
static/
  images/
    products/            # Product images go here
templates/
  admin/
    product_list.html    # Admin product list
    product_edit.html    # Admin product edit/create
  shop.html              # Public shop page
  product_detail.html    # Product detail page
  cart.html              # Shopping cart
```

## Notes

- **Prices are stored in cents** (e.g., $19.99 = 1999)
- **Only published products** appear in the shop (`/shop`)
- **Images must exist** in `static/images/products/` before referencing
- **Session-based cart** - cart data is temporary
- **No authentication** - admin routes are public (add auth if needed for production)

## Next Steps (Optional Enhancements)

- Add authentication for admin routes
- Implement payment processing (Stripe/PayPal)
- Add order management system
- CSV import/export for products
- Image upload functionality (currently manual file placement)
- Search and filtering in shop
- Product variants (size, color options)

