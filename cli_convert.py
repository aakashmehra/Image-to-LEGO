import os
import sys
import importlib.util
import trimesh

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Image to LEGO STL Converter (CLI wrapper)")
    parser.add_argument("--input", type=str, required=True, help="Path to input image file")
    parser.add_argument("--output", type=str, required=True, help="Path to save output STL file")
    parser.add_argument("--mode", type=str, choices=["baseplate", "brick"], default="baseplate", help="Conversion mode")
    parser.add_argument("--studs", type=str, choices=["with", "none"], default="with", help="Include studs")
    parser.add_argument("--ring", type=str, choices=["add", "none"], default="none", help="Add keychain ring")
    parser.add_argument("--height", type=float, default=40.0, help="Target height in mm")
    parser.add_argument("--width", type=float, default=None, help="Target width in mm")
    parser.add_argument("--thickness", type=float, default=5.5, help="Target thickness in mm")
    
    args = parser.parse_args()
    
    # Dynamically import image-to-lego.py
    script_dir = os.path.dirname(os.path.abspath(__file__))
    script_path = os.path.join(script_dir, "image-to-lego.py")
    if not os.path.exists(script_path):
        print(f"Error: image-to-lego.py not found at {script_path}", file=sys.stderr)
        sys.exit(1)
        
    spec = importlib.util.spec_from_file_location("image_to_lego", script_path)
    img_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(img_mod)
    
    # Calculate settings matching original logic
    base_thickness = 1.62
    thickness = base_thickness * (3 if args.mode == "brick" else 1)
    include_studs = (args.studs == "with")
    include_ring = (args.ring == "add")
    
    pixel_coordinates, inverted_pixel_coordinates = img_mod.image_to_pixel_coordinates(args.input, black_color=0, white_color=255)
    
    # Calculate px_to_mm dynamically so height (Y) is args.height
    width_px = max(y for x, y in pixel_coordinates) + 1
    length_px = max(x for x, y in pixel_coordinates) + 1
    
    px_to_mm = args.height / width_px
    
    gen_width = length_px * px_to_mm
    gen_height = args.height
    
    target_width = args.width if args.width is not None else gen_width
    target_height = args.height
    
    mesh = img_mod.pixel_coordinates_to_trimesh(pixel_coordinates, px_to_mm=px_to_mm, thickness_mm=thickness+0.3, margin_px=0)
    canvas = img_mod.mesh_canvas(pixel_coordinates, px_to_mm=px_to_mm, thickness_mm=thickness - 0.6, margin_px=0)
    
    mesh = img_mod.center_mesh_on_floor(mesh)
    canvas = img_mod.center_mesh_on_floor(canvas)
    
    # Scale width (X) and height (Y) symmetrically to match targets
    scale_x = target_width / gen_width
    scale_y = target_height / gen_height
    if abs(scale_x - 1.0) > 1e-5 or abs(scale_y - 1.0) > 1e-5:
        mesh.vertices[:, 0] *= scale_x
        mesh.vertices[:, 1] *= scale_y
        canvas.vertices[:, 0] *= scale_x
        canvas.vertices[:, 1] *= scale_y
    
    parts = [canvas, mesh]
    if include_studs:
        # Create studs based on the scaled geometry bounds
        baseplate = img_mod.create_stud_mesh(mesh, thickness)
        baseplate = img_mod.center_mesh_on_floor(baseplate)
        parts.append(baseplate)
        
    union_mesh = trimesh.util.concatenate(parts)
    
    if include_ring:
        try:
            ring_path = os.path.join(script_dir, 'ring_attachment.stl')
            if not os.path.exists(ring_path):
                print(f"Warning: ring_attachment.stl not found at {ring_path}. Skipping ring.", file=sys.stderr)
            else:
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
                tz = 0
                ring_mesh.apply_translation((tx, ty, tz))

                union_mesh = trimesh.util.concatenate([union_mesh, ring_mesh])
        except Exception as e:
            print("Failed to add keyring attachment:", e, file=sys.stderr)

    # Translate so min Z is 0
    min_z = union_mesh.bounds[0][2]
    union_mesh.apply_translation((0, 0, -min_z))
    
    # Force thickness to be exactly args.thickness in Z
    min_z, max_z = union_mesh.bounds[0][2], union_mesh.bounds[1][2]
    current_thickness = max_z - min_z
    if current_thickness > 0:
        scale_z = args.thickness / current_thickness
        union_mesh.vertices[:, 2] *= scale_z
        
    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    img_mod.save_mesh(union_mesh, args.output)
    
    # Print the physical dimensions for the user
    print("\nGenerated mesh physical dimensions:")
    print(f"Width (X): {union_mesh.extents[0]:.2f} mm")
    print(f"Height (Y): {union_mesh.extents[1]:.2f} mm")
    print(f"Thickness (Z): {union_mesh.extents[2]:.2f} mm")

if __name__ == "__main__":
    main()
