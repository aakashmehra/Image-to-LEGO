import os
import uuid
from datetime import datetime

from flask import Flask, render_template, request, redirect, url_for, send_from_directory, send_file, abort, flash, session, jsonify
from werkzeug.utils import secure_filename
from product_store import (
    load_products, save_products, get_product, create_product, update_product, delete_product,
    get_published_products, format_price
)
from coupon_store import (
    load_coupons, save_coupons, get_coupon, get_coupon_by_code, create_coupon, update_coupon,
    delete_coupon, increment_coupon_usage, validate_coupon
)
from analytics_store import record_visit, get_analytics_summary
from admin_auth import (
    save_admin_password, verify_password, admin_password_exists,
    get_admin_password_hash
)

# Reuse the existing conversion logic from image-to-lego.py (hyphenated filename)
import importlib.util
_SCRIPT_PATH = os.path.join(os.path.dirname(__file__), "image-to-lego.py")
_spec = importlib.util.spec_from_file_location("image_to_lego", _SCRIPT_PATH)
_img_mod = importlib.util.module_from_spec(_spec) if _spec else None
if _spec and _spec.loader:  # type: ignore[truthy-function]
    _spec.loader.exec_module(_img_mod)  # type: ignore[attr-defined]
else:
    raise RuntimeError("Unable to load image-to-lego.py module")

# Pull required functions from the loaded module
image_to_pixel_coordinates = _img_mod.image_to_pixel_coordinates
pixel_coordinates_to_trimesh = _img_mod.pixel_coordinates_to_trimesh
mesh_canvas = _img_mod.mesh_canvas
create_stud_mesh = _img_mod.create_stud_mesh
center_mesh_on_floor = _img_mod.center_mesh_on_floor
save_mesh = _img_mod.save_mesh


# --- Configuration ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
OUTPUT_FOLDER = os.path.join(BASE_DIR, "outputs")
PRODUCT_IMAGES_FOLDER = os.path.join(BASE_DIR, "static", "images", "products")

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "bmp"}
ALLOWED_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "bmp", "webp"}

DEFAULT_PX_TO_MM = 0.264
DEFAULT_THICKNESS_MM = 1.7


def ensure_dirs():
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    os.makedirs(OUTPUT_FOLDER, exist_ok=True)
    os.makedirs(PRODUCT_IMAGES_FOLDER, exist_ok=True)


def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

def allowed_image_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_IMAGE_EXTENSIONS


def run_conversion(image_path: str, output_path: str, thickness_mm: float, px_to_mm: float, include_studs: bool, include_ring: bool) -> str:
    """
    Calls the functions from image-to-lego.py to generate a single STL output
    (canvas + mesh + baseplate union). Returns the path to the STL file.
    """
    # Colors expected by the existing code
    black_color = 0
    white_color = 255

    pixel_coordinates, inverted_pixel_coordinates = image_to_pixel_coordinates(
        image_path, black_color, white_color
    )

    # Calculate px_to_mm dynamically so height (Y) is exactly 40mm (proportional scaling)
    width_px = max(y for x, y in pixel_coordinates) + 1
    px_to_mm = 40.0 / width_px

    mesh = pixel_coordinates_to_trimesh(
        pixel_coordinates, px_to_mm=px_to_mm, thickness_mm=thickness_mm + 0.3, margin_px=0
    )
    canvas = mesh_canvas(
        pixel_coordinates, px_to_mm=px_to_mm, thickness_mm=thickness_mm - 0.6, margin_px=0
    )

    mesh = center_mesh_on_floor(mesh)
    parts = [canvas, mesh]
    if include_studs:
        baseplate = create_stud_mesh(mesh, thickness_mm)
        baseplate = center_mesh_on_floor(baseplate)
        parts.append(baseplate)

    import trimesh  # local import to avoid unused import warnings if tooling analyzes

    union_mesh = trimesh.util.concatenate(parts)

    if include_ring:
        # Merge pre-modeled ring attachment STL at extreme top-right; 25% overlaps the body.
        try:
            ring_path = os.path.join(BASE_DIR, 'ring_attachment.stl')
            ring_mesh = trimesh.load(ring_path, force='mesh')
            if hasattr(ring_mesh, 'geometry'):
                ring_mesh = trimesh.util.concatenate(tuple(ring_mesh.geometry.values()))

            # Place ring so its base aligns with the current base of the model (canvas floor)
            rmin, rmax = ring_mesh.bounds
            base_z = union_mesh.bounds[0][2]
            ring_mesh.apply_translation((0, 0, base_z - rmin[2]))
            rmin, rmax = ring_mesh.bounds
            rsize = rmax - rmin

            # Target location: outside at +X/+Y with 40% overlap
            min_b, max_b = union_mesh.bounds
            f = 0.40  # fraction of ring diameter that should be inside the main body
            desired_cx = max_b[0] + (0.5 - f) * rsize[0]
            desired_cy = max_b[1] + (0.5 - f) * rsize[1]
            current_cx = (rmin[0] + rmax[0]) / 2.0
            current_cy = (rmin[1] + rmax[1]) / 2.0
            tx = desired_cx - current_cx
            ty = desired_cy - current_cy
            tz = 0  # z already aligned to base via previous translation
            ring_mesh.apply_translation((tx, ty, tz))

            union_mesh = trimesh.util.concatenate([union_mesh, ring_mesh])
        except Exception:
            pass
            
    min_z = union_mesh.bounds[0][2]
    union_mesh.apply_translation((0, 0, -min_z))

    # Force thickness to be exactly 5.5mm in Z
    min_z, max_z = union_mesh.bounds[0][2], union_mesh.bounds[1][2]
    current_thickness = max_z - min_z
    if current_thickness > 0:
        scale_z = 5.5 / current_thickness
        union_mesh.vertices[:, 2] *= scale_z

    out_path = output_path
    save_mesh(union_mesh, out_path)

    # No preview generation (simplified output path flow)

    return out_path


def create_app() -> Flask:
    ensure_dirs()
    app = Flask(__name__)
    app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
    app.config["OUTPUT_FOLDER"] = OUTPUT_FOLDER
    # Simple secret for flash messages (not critical here)
    app.secret_key = os.environ.get("FLASK_SECRET_KEY", "image-to-lego-secret")
    
    # Admin authentication middleware
    @app.before_request
    def check_admin_auth():
        # Skip auth check for login, setup, logout, and static files
        if request.path.startswith('/static'):
            return
        if request.path in ['/admin/login', '/admin/setup', '/admin/logout']:
            return
        
        # If accessing admin routes
        if request.path.startswith('/admin'):
            # Check if password is set
            if not admin_password_exists():
                # Redirect to setup if no password exists
                if request.path != '/admin/setup':
                    return redirect(url_for('admin_setup'))
                return
            
            # Check if user is authenticated
            if not session.get('admin_authenticated', False):
                # Redirect to login
                if request.path != '/admin/login':
                    return redirect(url_for('admin_login'))
                return
    
    # Analytics tracking middleware
    @app.before_request
    def track_visit():
        # Skip tracking for admin pages and static files
        if not request.path.startswith('/admin') and not request.path.startswith('/static'):
            # Get IP address
            ip_address = request.headers.get('CF-Connecting-IP', '')  # Cloudflare
            if not ip_address:
                ip_address = request.headers.get('X-Forwarded-For', '').split(',')[0].strip()
            if not ip_address:
                ip_address = request.remote_addr or 'Unknown'
            
            # Get country - try multiple methods
            country = request.headers.get('CF-IPCountry', '')  # Cloudflare
            if not country or country == 'XX' or country == 'Unknown':
                # Try X-Forwarded-For country header
                country = request.headers.get('CF-IpCountry', '')
            if not country or country == 'XX' or country == 'Unknown':
                # Try geoip header
                country = request.headers.get('X-Country-Code', '')
            if not country or country == 'Unknown':
                # Try to use IP-based geolocation (simple fallback)
                # For better accuracy, you'd want to use a geolocation service
                country = 'Unknown'
            
            user_agent = request.headers.get('User-Agent', '')
            referrer = request.headers.get('Referer', '')
            record_visit(
                page=request.path,
                country=country or 'Unknown',
                ip_address=ip_address,
                user_agent=user_agent,
                referrer=referrer
            )

    @app.get("/")
    def index():
        cart_items = session.get('cart', [])
        cart_count = sum(item.get('quantity', 0) for item in cart_items)
        return render_template("index.html", cart_count=cart_count)

    @app.get("/convert")
    def convert():
        cart_items = session.get('cart', [])
        cart_count = sum(item.get('quantity', 0) for item in cart_items)
        return render_template(
            "image_to_lego.html",
            default_thickness=DEFAULT_THICKNESS_MM,
            default_px_to_mm=DEFAULT_PX_TO_MM,
            cart_count=cart_count,
        )

    @app.post("/upload")
    def upload():
        if "file" not in request.files:
            flash("No file part in the request")
            return redirect(url_for("index"))

        file = request.files["file"]
        if file.filename == "":
            flash("No file selected")
            return redirect(url_for("index"))

        if not allowed_file(file.filename):
            flash("Unsupported file type. Please upload PNG/JPG/GIF/BMP.")
            return redirect(url_for("index"))

        # Parse options
        # Thickness selection logic: baseplate -> 1.62, brick -> triple (4.86)
        mode = request.form.get("mode", "baseplate")
        base_thickness = 1.62
        thickness_mm = base_thickness * (3 if mode == "brick" else 1)

        # Include studs toggle
        studs_choice = request.form.get("studs", "with")
        include_studs = (studs_choice != "none")
        ring_choice = request.form.get("keyring", "none")
        include_ring = (ring_choice != "none")

        try:
            px_to_mm = float(request.form.get("px_to_mm", DEFAULT_PX_TO_MM))
        except ValueError:
            px_to_mm = DEFAULT_PX_TO_MM

        safe_name = secure_filename(file.filename)
        # Save upload using the same name as provided by the user
        upload_path = os.path.join(UPLOAD_FOLDER, safe_name)
        file.save(upload_path)

        # Output file: single file named after the image base name in outputs/
        suggested_name = os.path.splitext(safe_name)[0] + ".stl"
        final_output_path = os.path.join(OUTPUT_FOLDER, suggested_name)

        try:
            stl_path = run_conversion(upload_path, final_output_path, thickness_mm, px_to_mm, include_studs, include_ring)
        except Exception as exc:  # noqa: BLE001 - show friendly page
            # Write a tiny log for troubleshooting
            os.makedirs(OUTPUT_FOLDER, exist_ok=True)
            with open(os.path.join(OUTPUT_FOLDER, "process.log"), "a") as fh:
                fh.write(f"Error while processing: {exc}\n")
            return render_template("error.html", message=str(exc)), 500

        stl_filename = os.path.basename(stl_path)
        cart_items = session.get('cart', [])
        cart_count = sum(item.get('quantity', 0) for item in cart_items)
        return render_template(
            "image_to_lego.html",
            default_thickness=DEFAULT_THICKNESS_MM,
            default_px_to_mm=DEFAULT_PX_TO_MM,
            download_ready=True,
            filename=stl_filename,
            download_url=url_for("download", filename=stl_filename),
            suggested_name=suggested_name,
            open_modal=True,
            cart_count=cart_count,
        )

    @app.get("/download/<filename>")
    def download(filename: str):
        return send_from_directory(OUTPUT_FOLDER, filename, as_attachment=True)

    @app.get("/file/<filename>")
    def serve_file(filename: str):
        file_path = os.path.join(OUTPUT_FOLDER, filename)
        # Serve with STL mimetype to help some loaders
        return send_file(file_path, mimetype="model/stl")

    @app.get("/about")
    def about():
        cart_items = session.get('cart', [])
        cart_count = sum(item.get('quantity', 0) for item in cart_items)
        return render_template("about.html", cart_count=cart_count)

    @app.get("/shop")
    def shop():
        products = get_published_products()
        cart_items = session.get('cart', [])
        cart_count = sum(item.get('quantity', 0) for item in cart_items)
        
        # Get filter parameters
        min_price = request.args.get('min_price', type=int)
        max_price = request.args.get('max_price', type=int)
        category = request.args.get('category', '')
        color = request.args.get('color', '')
        size = request.args.get('size', '')
        
        # Apply filters
        filtered_products = products
        if min_price is not None:
            filtered_products = [p for p in filtered_products if (p.get('price', 0) / 100) >= min_price]
        if max_price is not None:
            filtered_products = [p for p in filtered_products if (p.get('price', 0) / 100) <= max_price]
        if category:
            filtered_products = [p for p in filtered_products if category in p.get('categories', [])]
        if color:
            filtered_products = [p for p in filtered_products if any(
                v.get('option_type') == 'color' and (v.get('option_name', '').lower() == color.lower() or v.get('option_value', '').lower() == color.lower())
                for v in p.get('variants', [])
            )]
        if size:
            filtered_products = [p for p in filtered_products if any(
                v.get('option_type') != 'color' and v.get('option_type') != 'addon' and
                (v.get('option_name', '').lower() == size.lower() or v.get('option_value', '').lower() == size.lower())
                for v in p.get('variants', [])
            )]
        
        # Get unique values for filters
        all_categories = sorted(set([cat for p in products for cat in p.get('categories', [])]))
        all_colors = sorted(set([v.get('option_name', '') for p in products for v in p.get('variants', []) if v.get('option_type') == 'color' and v.get('option_name')]))
        all_sizes = sorted(set([v.get('option_name', '') for p in products for v in p.get('variants', []) if v.get('option_type') != 'color' and v.get('option_type') != 'addon' and v.get('option_name')]))
        
        # Get price range
        prices = [p.get('price', 0) / 100 for p in products]
        min_product_price = min(prices) if prices else 0
        max_product_price = max(prices) if prices else 1000
        
        return render_template(
            "shop.html",
            products=filtered_products,
            all_products=products,
            cart_count=cart_count,
            all_categories=all_categories,
            all_colors=all_colors,
            all_sizes=all_sizes,
            min_product_price=min_product_price,
            max_product_price=max_product_price,
            current_filters={
                'min_price': min_price,
                'max_price': max_price,
                'category': category,
                'color': color,
                'size': size
            }
        )

    @app.get("/product/<slug>")
    def product_detail(slug):
        products = load_products()
        product = next((p for p in products if p.get('slug') == slug), None)
        cart_items = session.get('cart', [])
        cart_count = sum(item.get('quantity', 0) for item in cart_items)
        return render_template("product_detail.html", product=product, cart_count=cart_count)

    @app.post("/cart/add")
    def cart_add():
        product_id = request.form.get('product_id')
        variant_id = request.form.get('variant_id')
        addon_ids = request.form.getlist('addon_ids[]')
        quantity = int(request.form.get('quantity', 1))
        
        products = load_products()
        product = next((p for p in products if p.get('id') == product_id), None)
        
        if not product:
            flash('Product not found', 'error')
            return redirect(url_for('shop'))
        
        # Get variant if selected
        variant = None
        variant_price = product.get('price', 0)
        if variant_id and product.get('variants'):
            variant = next((v for v in product.get('variants', []) if v.get('id') == variant_id), None)
            if variant:
                variant_price = variant.get('price', variant_price)
        
        # Calculate total price including addons
        total_addon_price = 0
        selected_addons = []
        if addon_ids and product.get('variants'):
            for addon_id in addon_ids:
                addon = next((v for v in product.get('variants', []) if v.get('id') == addon_id and v.get('option_type') == 'addon'), None)
                if addon:
                    total_addon_price += addon.get('price', 0)
                    selected_addons.append(addon.get('option_name', ''))
        
        final_price = variant_price + total_addon_price
        
        # Check inventory
        if product.get('inventory_policy') == 'deny' and product.get('inventory', 0) < quantity:
            flash('Not enough inventory', 'error')
            return redirect(url_for('product_detail', slug=product.get('slug')))
        
        # Add to cart (session-based)
        if 'cart' not in session:
            session['cart'] = []
        
        cart = session['cart']
        
        # Build cart item title
        item_title = product.get('title')
        if variant and variant.get('option_name'):
            item_title += f" - {variant.get('option_name')}"
        if selected_addons:
            item_title += f" (+ {', '.join(selected_addons)})"
        
        cart.append({
            'product_id': product_id,
            'variant_id': variant_id,
            'addon_ids': addon_ids,
            'quantity': quantity,
            'price': final_price,
            'title': item_title,
            'slug': product.get('slug'),
            'image': product.get('images', [None])[0] if product.get('images') else None
        })
        
        session['cart'] = cart
        flash(f'Added {quantity} {item_title} to cart', 'success')
        return redirect(url_for('product_detail', slug=product.get('slug')))

    @app.get("/cart")
    def cart_view():
        cart_items = session.get('cart', [])
        products = load_products()
        cart_count = sum(item.get('quantity', 0) for item in cart_items)
        
        # Enrich cart items with full product data
        enriched_cart = []
        total = 0
        for item in cart_items:
            product = next((p for p in products if p.get('id') == item.get('product_id')), None)
            if product:
                item_total = item.get('quantity', 0) * item.get('price', 0)
                total += item_total
                enriched_cart.append({
                    **item,
                    'product': product,
                    'item_total': item_total
                })
        
        return render_template("cart.html", cart_items=enriched_cart, total=total, cart_count=cart_count)

    @app.post("/cart/update")
    def cart_update():
        product_id = request.form.get('product_id')
        quantity = int(request.form.get('quantity', 0))
        
        cart = session.get('cart', [])
        if quantity <= 0:
            cart = [item for item in cart if item.get('product_id') != product_id]
        else:
            for item in cart:
                if item.get('product_id') == product_id:
                    item['quantity'] = quantity
                    break
        
        session['cart'] = cart
        flash('Cart updated', 'success')
        return redirect(url_for('cart_view'))

    @app.post("/cart/remove")
    def cart_remove():
        product_id = request.form.get('product_id')
        cart = session.get('cart', [])
        cart = [item for item in cart if item.get('product_id') != product_id]
        session['cart'] = cart
        flash('Item removed from cart', 'success')
        return redirect(url_for('cart_view'))

    # Admin Authentication Routes
    @app.get("/admin/setup")
    def admin_setup():
        """Setup admin password (first time only)"""
        if admin_password_exists():
            flash('Admin password already set. Please login.', 'info')
            return redirect(url_for('admin_login'))
        return render_template("admin/setup.html")
    
    @app.post("/admin/setup")
    def admin_setup_post():
        """Save admin password"""
        if admin_password_exists():
            flash('Admin password already set. Please login.', 'info')
            return redirect(url_for('admin_login'))
        
        password = request.form.get('password', '').strip()
        confirm_password = request.form.get('confirm_password', '').strip()
        
        if not password:
            flash('Password is required', 'error')
            return redirect(url_for('admin_setup'))
        
        if password != confirm_password:
            flash('Passwords do not match', 'error')
            return redirect(url_for('admin_setup'))
        
        if len(password) < 6:
            flash('Password must be at least 6 characters', 'error')
            return redirect(url_for('admin_setup'))
        
        save_admin_password(password)
        flash('Admin password created successfully! Please login.', 'success')
        print(f"\n{'='*60}")
        print("ADMIN PASSWORD SETUP COMPLETE")
        print(f"{'='*60}")
        print(f"Password: {password}")
        print(f"Please copy this password and use it to login.")
        print(f"{'='*60}\n")
        return redirect(url_for('admin_login'))
    
    @app.get("/admin/login")
    def admin_login():
        """Admin login page"""
        if not admin_password_exists():
            return redirect(url_for('admin_setup'))
        return render_template("admin/login.html")
    
    @app.post("/admin/login")
    def admin_login_post():
        """Authenticate admin"""
        password = request.form.get('password', '').strip()
        
        if verify_password(password):
            session['admin_authenticated'] = True
            flash('Login successful!', 'success')
            return redirect(url_for('admin_dashboard'))
        else:
            flash('Invalid password', 'error')
            return redirect(url_for('admin_login'))
    
    @app.get("/admin/logout")
    def admin_logout():
        """Logout admin"""
        session.pop('admin_authenticated', None)
        flash('Logged out successfully', 'success')
        return redirect(url_for('admin_login'))
    
    # Admin Routes
    @app.get("/admin")
    def admin_dashboard():
        analytics = get_analytics_summary()
        products = load_products()
        coupons = load_coupons()
        active_coupons = [c for c in coupons if c.get('status') == 'active']
        return render_template(
            "admin/dashboard.html",
            analytics=analytics,
            product_count=len(products),
            coupon_count=len(active_coupons)
        )
    
    @app.get("/admin/products")
    def admin_product_list():
        products = load_products()
        return render_template("admin/product_list.html", products=products)

    @app.get("/admin/products/create")
    def admin_product_create():
        # Get all products to extract existing categories
        all_products = load_products()
        return render_template("admin/product_edit.html", product=None, all_products=all_products)

    @app.post("/admin/products/create")
    def admin_product_create_post():
        # Handle image uploads
        uploaded_images = []
        if 'product_images' in request.files:
            files = request.files.getlist('product_images')
            for file in files:
                if file and file.filename and allowed_image_file(file.filename):
                    filename = secure_filename(file.filename)
                    # Add timestamp to avoid conflicts
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_")
                    filename = timestamp + filename
                    file_path = os.path.join(PRODUCT_IMAGES_FOLDER, filename)
                    file.save(file_path)
                    uploaded_images.append(f"images/products/{filename}")
        
        # Also check for image_urls from textarea
        textarea_images = [img.strip() for img in request.form.get('image_urls', '').split('\n') if img.strip()]
        all_images = uploaded_images + textarea_images
        
        # Convert price from dollars to cents
        price_dollars = float(request.form.get('price', 0) or 0)
        compare_price_dollars = float(request.form.get('compare_at_price', 0) or 0)
        
        # Build variants from options
        variants = []
        
        # Color options
        color_names = request.form.getlist('color_names[]')
        color_values = request.form.getlist('color_values[]')
        for i, (name, value) in enumerate(zip(color_names, color_values)):
            if name and value:
                variants.append({
                    'id': str(uuid.uuid4()),
                    'option_type': 'color',
                    'option_name': name.strip(),
                    'option_value': value.strip(),
                    'price': int(price_dollars * 100),  # Use base price
                    'inventory': int(request.form.get('inventory', 0)),
                    'sku': request.form.get('sku', ''),
                })
        
        # Custom options
        custom_types = request.form.getlist('custom_option_types[]')
        custom_names = request.form.getlist('custom_option_names[]')
        custom_prices = request.form.getlist('custom_option_prices[]')
        for i, (opt_type, name, price_str) in enumerate(zip(custom_types, custom_names, custom_prices)):
            if opt_type and name:
                try:
                    variant_price = int(float(price_str or 0) * 100)
                except ValueError:
                    variant_price = int(price_dollars * 100)
                variants.append({
                    'id': str(uuid.uuid4()),
                    'option_type': opt_type.strip().lower(),
                    'option_name': name.strip(),
                    'option_value': name.strip(),
                    'price': variant_price,
                    'inventory': int(request.form.get('inventory', 0)),
                    'sku': request.form.get('sku', ''),
                })
        
        # Addon options
        addon_names = request.form.getlist('addon_names[]')
        addon_prices = request.form.getlist('addon_prices[]')
        for i, (name, price_str) in enumerate(zip(addon_names, addon_prices)):
            if name:
                try:
                    addon_price = int(float(price_str or 0) * 100)
                except ValueError:
                    addon_price = 0
                variants.append({
                    'id': str(uuid.uuid4()),
                    'option_type': 'addon',
                    'option_name': name.strip(),
                    'option_value': name.strip(),
                    'price': addon_price,
                    'inventory': int(request.form.get('inventory', 0)),
                    'sku': request.form.get('sku', ''),
                })
        
        product_data = {
            'title': request.form.get('title'),
            'slug': request.form.get('slug'),
            'short_description': request.form.get('short_description', ''),
            'description': request.form.get('description', ''),
            'price': int(price_dollars * 100),  # Convert dollars to cents
            'compare_at_price': int(compare_price_dollars * 100),
            'sku': request.form.get('sku', ''),
            'inventory': int(request.form.get('inventory', 0)),
            'inventory_policy': request.form.get('inventory_policy', 'continue'),
            'status': request.form.get('status', 'draft'),
            'categories': [c.strip() for c in request.form.get('categories', '').split(',') if c.strip()],
            'tags': [t.strip() for t in request.form.get('tags', '').split(',') if t.strip()],
            'images': all_images if all_images else [],
            'variants': variants,
        }
        
        product = create_product(product_data)
        flash(f'Product "{product.get("title")}" created successfully!', 'success')
        return redirect(url_for('admin_product_list'))

    @app.get("/admin/products/<product_id>/edit")
    def admin_product_edit(product_id):
        product = get_product(product_id)
        if not product:
            flash('Product not found', 'error')
            return redirect(url_for('admin_product_list'))
        # Get all products to extract existing categories
        all_products = load_products()
        return render_template("admin/product_edit.html", product=product, all_products=all_products)

    @app.post("/admin/products/<product_id>/edit")
    def admin_product_edit_post(product_id):
        # Get existing product to preserve existing images
        existing_product = get_product(product_id)
        existing_images = existing_product.get('images', []) if existing_product else []
        
        # Handle image uploads
        uploaded_images = []
        if 'product_images' in request.files:
            files = request.files.getlist('product_images')
            for file in files:
                if file and file.filename and allowed_image_file(file.filename):
                    filename = secure_filename(file.filename)
                    # Add timestamp to avoid conflicts
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_")
                    filename = timestamp + filename
                    file_path = os.path.join(PRODUCT_IMAGES_FOLDER, filename)
                    file.save(file_path)
                    uploaded_images.append(f"images/products/{filename}")
        
        # Also check for image_urls from textarea
        textarea_images = [img.strip() for img in request.form.get('image_urls', '').split('\n') if img.strip()]
        
        # Merge: new uploaded images + textarea images + existing images (preserve existing)
        all_images = uploaded_images + textarea_images + existing_images
        
        # Remove duplicates while preserving order
        seen = set()
        unique_images = []
        for img in all_images:
            if img not in seen:
                seen.add(img)
                unique_images.append(img)
        all_images = unique_images
        
        # Convert price from dollars to cents
        price_dollars = float(request.form.get('price', 0) or 0)
        compare_price_dollars = float(request.form.get('compare_at_price', 0) or 0)
        
        # Build variants from options
        variants = []
        
        # Color options
        color_names = request.form.getlist('color_names[]')
        color_values = request.form.getlist('color_values[]')
        for i, (name, value) in enumerate(zip(color_names, color_values)):
            if name and value:
                variants.append({
                    'id': str(uuid.uuid4()),
                    'option_type': 'color',
                    'option_name': name.strip(),
                    'option_value': value.strip(),
                    'price': int(price_dollars * 100),  # Use base price
                    'inventory': int(request.form.get('inventory', 0)),
                    'sku': request.form.get('sku', ''),
                })
        
        # Custom options
        custom_types = request.form.getlist('custom_option_types[]')
        custom_names = request.form.getlist('custom_option_names[]')
        custom_prices = request.form.getlist('custom_option_prices[]')
        for i, (opt_type, name, price_str) in enumerate(zip(custom_types, custom_names, custom_prices)):
            if opt_type and name:
                try:
                    variant_price = int(float(price_str or 0) * 100)
                except ValueError:
                    variant_price = int(price_dollars * 100)
                variants.append({
                    'id': str(uuid.uuid4()),
                    'option_type': opt_type.strip().lower(),
                    'option_name': name.strip(),
                    'option_value': name.strip(),
                    'price': variant_price,
                    'inventory': int(request.form.get('inventory', 0)),
                    'sku': request.form.get('sku', ''),
                })
        
        # Addon options
        addon_names = request.form.getlist('addon_names[]')
        addon_prices = request.form.getlist('addon_prices[]')
        for i, (name, price_str) in enumerate(zip(addon_names, addon_prices)):
            if name:
                try:
                    addon_price = int(float(price_str or 0) * 100)
                except ValueError:
                    addon_price = 0
                variants.append({
                    'id': str(uuid.uuid4()),
                    'option_type': 'addon',
                    'option_name': name.strip(),
                    'option_value': name.strip(),
                    'price': addon_price,
                    'inventory': int(request.form.get('inventory', 0)),
                    'sku': request.form.get('sku', ''),
                })
        
        product_data = {
            'title': request.form.get('title'),
            'slug': request.form.get('slug'),
            'short_description': request.form.get('short_description', ''),
            'description': request.form.get('description', ''),
            'price': int(price_dollars * 100),  # Convert dollars to cents
            'compare_at_price': int(compare_price_dollars * 100),
            'sku': request.form.get('sku', ''),
            'inventory': int(request.form.get('inventory', 0)),
            'inventory_policy': request.form.get('inventory_policy', 'continue'),
            'status': request.form.get('status', 'draft'),
            'categories': [c.strip() for c in request.form.get('categories', '').split(',') if c.strip()],
            'tags': [t.strip() for t in request.form.get('tags', '').split(',') if t.strip()],
            'images': all_images if all_images else [],
            'variants': variants,
        }
        
        product = update_product(product_id, product_data)
        if product:
            flash(f'Product "{product.get("title")}" updated successfully!', 'success')
            return redirect(url_for('admin_product_list'))
        else:
            flash('Product not found', 'error')
            return redirect(url_for('admin_product_list'))

    @app.post("/admin/products/<product_id>/delete")
    def admin_product_delete(product_id):
        product = get_product(product_id)
        if product:
            delete_product(product_id)
            flash(f'Product "{product.get("title")}" deleted successfully!', 'success')
        else:
            flash('Product not found', 'error')
        return redirect(url_for('admin_product_list'))
    
    # Coupon Routes
    @app.get("/admin/coupons")
    def admin_coupon_list():
        coupons = load_coupons()
        return render_template("admin/coupon_list.html", coupons=coupons)
    
    @app.get("/admin/coupons/create")
    def admin_coupon_create():
        return render_template("admin/coupon_edit.html", coupon=None)
    
    @app.post("/admin/coupons/create")
    def admin_coupon_create_post():
        discount_value = float(request.form.get('discount_value', 0) or 0)
        discount_type = request.form.get('discount_type', 'percentage')
        
        # Convert to cents if fixed amount
        if discount_type == 'fixed':
            discount_value = int(discount_value * 100)
        
        coupon_data = {
            'code': request.form.get('code', '').strip().upper(),
            'description': request.form.get('description', ''),
            'discount_type': discount_type,
            'discount_value': discount_value,
            'minimum_amount': int(float(request.form.get('minimum_amount', 0) or 0) * 100),
            'maximum_discount': int(float(request.form.get('maximum_discount', 0) or 0) * 100),
            'usage_limit': int(request.form.get('usage_limit', 0) or 0),
            'status': request.form.get('status', 'active'),
            'valid_from': request.form.get('valid_from', ''),
            'valid_until': request.form.get('valid_until', ''),
        }
        
        coupon = create_coupon(coupon_data)
        flash(f'Coupon "{coupon.get("code")}" created successfully!', 'success')
        return redirect(url_for('admin_coupon_list'))
    
    @app.get("/admin/coupons/<coupon_id>/edit")
    def admin_coupon_edit(coupon_id):
        coupon = get_coupon(coupon_id)
        if not coupon:
            flash('Coupon not found', 'error')
            return redirect(url_for('admin_coupon_list'))
        return render_template("admin/coupon_edit.html", coupon=coupon)
    
    @app.post("/admin/coupons/<coupon_id>/edit")
    def admin_coupon_edit_post(coupon_id):
        discount_value = float(request.form.get('discount_value', 0) or 0)
        discount_type = request.form.get('discount_type', 'percentage')
        
        # Convert to cents if fixed amount
        if discount_type == 'fixed':
            discount_value = int(discount_value * 100)
        
        coupon_data = {
            'code': request.form.get('code', '').strip().upper(),
            'description': request.form.get('description', ''),
            'discount_type': discount_type,
            'discount_value': discount_value,
            'minimum_amount': int(float(request.form.get('minimum_amount', 0) or 0) * 100),
            'maximum_discount': int(float(request.form.get('maximum_discount', 0) or 0) * 100),
            'usage_limit': int(request.form.get('usage_limit', 0) or 0),
            'status': request.form.get('status', 'active'),
            'valid_from': request.form.get('valid_from', ''),
            'valid_until': request.form.get('valid_until', ''),
        }
        
        coupon = update_coupon(coupon_id, coupon_data)
        if coupon:
            flash(f'Coupon "{coupon.get("code")}" updated successfully!', 'success')
            return redirect(url_for('admin_coupon_list'))
        else:
            flash('Coupon not found', 'error')
            return redirect(url_for('admin_coupon_list'))
    
    @app.post("/admin/coupons/<coupon_id>/delete")
    def admin_coupon_delete(coupon_id):
        coupon = get_coupon(coupon_id)
        if coupon:
            delete_coupon(coupon_id)
            flash(f'Coupon "{coupon.get("code")}" deleted successfully!', 'success')
        else:
            flash('Coupon not found', 'error')
        return redirect(url_for('admin_coupon_list'))

    @app.get("/privacy-policy")
    def privacy_policy():
        cart_items = session.get('cart', [])
        cart_count = sum(item.get('quantity', 0) for item in cart_items)
        return render_template("privacy_policy.html", cart_count=cart_count)

    @app.get("/shipping-info")
    def shipping_info():
        cart_items = session.get('cart', [])
        cart_count = sum(item.get('quantity', 0) for item in cart_items)
        return render_template("shipping_info.html", cart_count=cart_count)

    @app.get("/commercial-disclosure")
    def commercial_disclosure():
        cart_items = session.get('cart', [])
        cart_count = sum(item.get('quantity', 0) for item in cart_items)
        return render_template("commercial_disclosure.html", cart_count=cart_count)

    @app.get("/health")
    def health():
        return ("OK", 200)

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5230, debug=True)


 