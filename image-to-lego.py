from PIL import Image, ImageOps
import trimesh
import numpy as np
import math
import os


def image_input():
    print("Please provide the path to the image file:")
    input_image = input("Enter the path to the image: ")
    black_color = 0
    white_color = 255
    image_path = input_image.strip("'")
    print(image_path)
    return image_path, black_color, white_color


def image_to_pixel_coordinates(image_path, black_color, white_color):
    print("Processing image...")
    image = Image.open(image_path)
    image = ImageOps.exif_transpose(image)
    image = image.convert("L")
    
    # Ensure longest side of image is width
    if image.height > image.width:
        image = image.rotate(90, expand=True)
        
    if image.width > 5000 or image.height > 5000:
        image = image.resize((max(1, image.width//8), max(1, image.height//8)), Image.LANCZOS)
    if image.width >= 2000 or image.height >= 2000:
        image = image.resize((max(1, image.width//6), max(1, image.height//6)), Image.LANCZOS)
    elif image.width >= 1000 or image.height >= 1000:
        image = image.resize((max(1, image.width//5), max(1, image.height//5)), Image.LANCZOS)
    elif image.width >= 500 or image.height >= 500:
        image = image.resize((max(1, image.width//3), max(1, image.height//3)), Image.LANCZOS)
    else:
        image = image.resize((max(1, image.width//2), max(1, image.height//2)), Image.LANCZOS)
    image = image.point(lambda x: 255 if x > 128 else 0, '1')
    width, height = image.size
    pixels = []
    inverted_pixels = []
    for left in range(width):
        for top in range(height):
            if image.getpixel((left, top)) == black_color:
                pixels.append((left, top))

    for left in range(width):
        for top in range(height):
            if image.getpixel((left, top)) == white_color:
                inverted_pixels.append((left, top))
    if len(pixels) >= len(inverted_pixels):
        print("More black pixels found in the image than white pixels.")
        return pixels, inverted_pixels
    elif len(inverted_pixels) >= len(pixels):
        print("More white pixels found in the image than black pixels.")
        return inverted_pixels, pixels
    else:
        print("Equal number of black and white pixels found in the image.")
        return pixels, inverted_pixels, True


def _rectangles_from_pixel_coords(pixel_coordinates):
    """
    Convert pixel coordinate list into merged rectangles using run-length merging.
    Returns list of rectangles as (x_start, x_end, y_start, y_end), inclusive indices.
    """
    if not pixel_coordinates:
        return []

    max_x = max(x for x, y in pixel_coordinates)
    max_y = max(y for x, y in pixel_coordinates)
    width_px = max_x + 1
    height_px = max_y + 1

    grid = np.zeros((height_px, width_px), dtype=bool)
    for x, y in pixel_coordinates:
        grid[y, x] = True

    rectangles = []
    prev_runs = {}

    for y in range(height_px):
        row = grid[y]
        true_idxs = np.where(row)[0]
        runs = []
        if true_idxs.size > 0:
            start = true_idxs[0]
            last = start
            for idx in true_idxs[1:]:
                if idx == last + 1:
                    last = idx
                else:
                    runs.append((start, last))
                    start = idx
                    last = idx
            runs.append((start, last))

        continued_keys = set()
        new_prev = {}

        for run in runs:
            key = (run[0], run[1])
            if key in prev_runs:
                rect = prev_runs[key]
                rect[3] = y
                new_prev[key] = rect
                continued_keys.add(key)
            else:
                new_prev[key] = [run[0], run[1], y, y]

        for key, rect in prev_runs.items():
            if key not in continued_keys:
                rectangles.append(tuple(rect))

        prev_runs = new_prev

    for rect in prev_runs.values():
        rectangles.append(tuple(rect))

    return rectangles


def pixel_coordinates_to_trimesh(pixel_coordinates, px_to_mm, thickness_mm, margin_px):
    if not pixel_coordinates:
        raise ValueError("No black pixels found in the image.")

    canvas_margin_mm = 0.0

    length_px = max(x for x, y in pixel_coordinates) + 1
    width_px  = max(y for x, y in pixel_coordinates) + 1

    content_mm_x = length_px * px_to_mm
    content_mm_y = width_px * px_to_mm

    canvas_mm_x = content_mm_x + 2 * canvas_margin_mm
    canvas_mm_y = content_mm_y + 2 * canvas_margin_mm

    box_dz = thickness_mm
    half_dz = box_dz / 2.0

    rectangles = _rectangles_from_pixel_coords(pixel_coordinates)

    meshes = []
    for (x0, x1, y0, y1) in rectangles:
        pixel_w = (x1 - x0 + 1)
        pixel_h = (y1 - y0 + 1)

        box_dx = pixel_w * px_to_mm
        box_dy = pixel_h * px_to_mm

        center_x_px = x0 + (pixel_w - 1) / 2.0 + 0.5
        center_y_px = y0 + (pixel_h - 1) / 2.0 + 0.5

        flipped_center_y_px = (width_px - 1) - (center_y_px - 0.5) + 0.5

        cx = canvas_margin_mm + (center_x_px + margin_px) * px_to_mm
        cy = canvas_margin_mm + (flipped_center_y_px + margin_px) * px_to_mm
        cz = half_dz

        box = trimesh.creation.box(extents=[box_dx, box_dy, box_dz])
        box.apply_translation((cx, cy, cz))
        meshes.append(box)

    if not meshes:
        box = trimesh.creation.box(extents=[px_to_mm, px_to_mm, box_dz])
        box.apply_translation((canvas_margin_mm + px_to_mm/2, canvas_margin_mm + px_to_mm/2, half_dz))
        return box

    combined = trimesh.util.concatenate(meshes)

    return combined


def mesh_canvas(pixel_coordinates, px_to_mm, thickness_mm, margin_px):
    thickness_mm = thickness_mm * 2
    length_px = max(x for x, y in pixel_coordinates) + 1
    width_px  = max(y for x, y in pixel_coordinates) + 1

    border_mm = 0.0  # No border on each side

    content_mm_x = length_px * px_to_mm
    content_mm_y = width_px * px_to_mm

    canvas = trimesh.creation.box(
        extents=[
            content_mm_x + border_mm * 2,
            content_mm_y + border_mm * 2,
            thickness_mm
        ]
    )
    return canvas


def create_stud_mesh(mesh, thickness):
    stl_size = (mesh.extents)
    x = max(float(stl_size[0]), 0.0)
    y = max(float(stl_size[1]), 0.0)
    z = max(float(stl_size[2]), 0.0)

    stud_spacing = 8
    stud_diameter = 4.9
    stud_radius = stud_diameter / 2
    stud_height = 5.5 - thickness

    stud_cylinders = []
    stud_cylinder = trimesh.creation.cylinder(radius=2.4, height=1.8)

    available_width = x
    available_height = y
    if available_width < stud_diameter or available_height < stud_diameter:
        return trimesh.Trimesh()

    num_studs_x = int(math.floor((available_width - stud_diameter) / stud_spacing) + 1)
    num_studs_y = int(math.floor((available_height - stud_diameter) / stud_spacing) + 1)

    num_studs_x = max(num_studs_x, 1)
    num_studs_y = max(num_studs_y, 1)

    stud_proto = trimesh.creation.cylinder(radius=stud_radius, height=stud_height, sections=64)
    stud_proto.apply_translation((0.0, 0.0, stud_height / 2.0))

    total_span_x = (num_studs_x - 1) * stud_spacing
    total_span_y = (num_studs_y - 1) * stud_spacing

    start_x = -(total_span_x / 2.0)
    start_y = -(total_span_y / 2.0)

    for ix in range(num_studs_x):
        for iy in range(num_studs_y):
            py = start_y + iy * stud_spacing
            px = start_x + ix * stud_spacing
            c = stud_proto.copy()
            c.apply_translation((px, py, 0))
            stud_cylinders.append(c)

    stud_cylinders_mesh = trimesh.util.concatenate(stud_cylinders)
    return stud_cylinders_mesh


def center_mesh_on_floor(mesh):
    if mesh is None:
        raise ValueError("Mesh is None")

    bounds = mesh.bounds
    min_bound = bounds[0]
    max_bound = bounds[1]

    center_x = (min_bound[0] + max_bound[0]) / 2.0
    center_y = (min_bound[1] + max_bound[1]) / 2.0

    tx = -center_x
    ty = -center_y

    tz = -min_bound[2]

    mesh.apply_translation((tx, ty, tz))
    return mesh



def save_mesh(mesh, output_path):
    print("Saving Mesh to", output_path)
    mesh.export(output_path)


if __name__ == "__main__":
    thickness = 1.6
    image_path, black_color, white_color = image_input()
    pixel_coordinates, inverted_pixel_coordinates = image_to_pixel_coordinates(image_path, black_color, white_color)
    
    # Calculate px_to_mm dynamically so height (Y) is exactly 40mm (proportional scaling)
    width_px = max(y for x, y in pixel_coordinates) + 1
    px_to_mm = 40.0 / width_px
    
    mesh = pixel_coordinates_to_trimesh(pixel_coordinates, px_to_mm=px_to_mm, thickness_mm=thickness+0.3, margin_px=0)
    canvas = mesh_canvas(pixel_coordinates, px_to_mm=px_to_mm, thickness_mm=thickness - 0.6, margin_px=0)
    mesh = center_mesh_on_floor(mesh)
    baseplate = create_stud_mesh(mesh, thickness)
    baseplate = center_mesh_on_floor(baseplate)
    union_mesh = trimesh.util.concatenate([canvas, mesh, baseplate])
    
    # Translate so min Z is 0
    min_z = union_mesh.bounds[0][2]
    union_mesh.apply_translation((0, 0, -min_z))
    
    # Force thickness to be exactly 5.5mm in Z
    min_z, max_z = union_mesh.bounds[0][2], union_mesh.bounds[1][2]
    current_thickness = max_z - min_z
    if current_thickness > 0:
        scale_z = 5.5 / current_thickness
        union_mesh.vertices[:, 2] *= scale_z
        
    os.makedirs("Image to LEGO", exist_ok=True)
    output_path = "Image to LEGO/union_output.stl"
    save_mesh(union_mesh, output_path)
    
    # Print the physical dimensions for the user
    print("\nGenerated mesh physical dimensions:")
    print(f"Width (X): {union_mesh.extents[0]:.2f} mm")
    print(f"Height (Y): {union_mesh.extents[1]:.2f} mm")
    print(f"Thickness (Z): {union_mesh.extents[2]:.2f} mm")

