# Image-to-LEGO (Flask) — Contents

This `contents.md` documents the Flask-based **Image-to-LEGO** online conversion tool. The app is deliberately **no-JavaScript** — everything is done server-side in Python/Flask and rendered with Jinja2 templates.

---

## Table of contents

1. Overview
2. Features
3. Project layout
4. Installation
5. Configuration
6. Running the app
7. Routes and behavior
8. HTML templates (no-JS)
9. File upload & security
10. Processing pipeline (image → voxels → STL)
11. Error handling & logs
12. Testing
13. Deployment notes
14. Troubleshooting
15. License

---

## 1. Overview

A simple Flask web application that accepts an image upload, converts the image to a pixel/voxel representation, generates one or more STL meshes (main mesh, inverted mesh, baseplate, union, or subtracted result), and returns downloadable STL files to the user. The server performs all processing in Python using libraries such as `Pillow`, `trimesh`, `numpy`, and `scikit-image` (for marching cubes), and optionally calls `openscad` if installed.

All user interaction occurs via classic HTML forms and server-generated pages (no client-side JavaScript). The app focuses on clarity, predictability, and safety.

---

## 2. Features

* Upload a raster image (PNG, JPG, GIF, BMP) or exported PNG of SVG.
* Choose options such as `px_to_mm`, `thickness_mm`, `margin_px`, and `voxel_pitch`.
* Generate and download the following outputs:

  * `output.stl` — mesh created from black pixels (or chosen color)
  * `inverted_output.stl` — inverted pixels mesh
  * `baseplate_output.stl` — stud grid mesh
  * `subtracted_final.stl` — result of subtracting inverted mesh from main mesh (voxel fallback if booleans fail)
* Server-side processing only — no JS required.
* Simple progress/status pages and friendly error messages.

---

## 3. Project layout (recommended)

```
image-to-lego-flask/
├── app.py                # main Flask app
├── contents.md           # this file
├── requirements.txt
├── templates/
│   ├── base.html
│   ├── index.html        # upload form
│   ├── status.html       # processing & result links
│   └── error.html
├── static/
│   └── css/
│       └── style.css
├── uploads/              # uploaded images (ensure not publicly served directly)
├── outputs/              # generated STLs and logs
├── modules/              # optional: processing helper modules
│   ├── image_io.py
│   └── mesh_utils.py
└── README.md
```

Notes:

* Keep `uploads/` and `outputs/` writeable by the app user. Protect these directories from arbitrary public listing.
* Put large or long-running tasks behind appropriate limits.

---

## 4. Installation

Create a virtual environment and install dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip setuptools wheel
pip install -r requirements.txt
```

A suggested `requirements.txt`:

```
Flask>=2.0
Pillow
trimesh
numpy
scikit-image
rtree
shapely
scipy
```

Notes for macOS (M1/arm64): `scikit-image` may be easier to install via `conda` or by upgrading `pip/setuptools/wheel` first.

If you want boolean engine integration, install OpenSCAD and ensure `openscad` is on your `PATH`.

---

## 5. Configuration

Use environment variables or a small `config.py` to configure important values:

```py
# config.py
UPLOAD_FOLDER = 'uploads'
OUTPUT_FOLDER = 'outputs'
MAX_CONTENT_LENGTH = 20 * 1024 * 1024  # 20 MB
ALLOWED_EXTENSIONS = {'png','jpg','jpeg','gif','bmp'}
DEFAULT_PX_TO_MM = 0.264
DEFAULT_THICKNESS_MM = 4.0
DEFAULT_MARGIN_PX = 0
DEFAULT_VOXEL_PITCH = 0.5
```

Load these values into the Flask `app.config` at startup.

---

## 6. Running the app (development)

```bash
export FLASK_APP=app.py
export FLASK_ENV=development
flask run --host=0.0.0.0 --port=5000
```

For production, run behind a WSGI server such as `gunicorn`:

```bash
gunicorn -w 4 -b 0.0.0.0:8000 app:app
```

---

## 7. Routes and behavior

Suggested endpoints (all server-side, no JS):

* `GET /` — show `index.html` with upload form and processing options.
* `POST /upload` — accept file upload and form data, validate and store file, then redirect to `/process/<job_id>` or `/status/<job_id>`.
* `GET /status/<job_id>` — show processing status and links to results when ready.
* `GET /download/<job_id>/<filename>` — stream the generated file as attachment.
* `GET /health` — simple healthcheck returning `200 OK`.

Processing policy:

* On `POST /upload`, the server should validate file type and save the file to `uploads/` with a unique job id (UUID + timestamp).
* Immediately run the processing function synchronously (or short tasks) — since you requested no JS, show a `status.html` after upload that refreshes (meta refresh) to poll server status if desired.

Important: For long jobs consider returning a `202 Accepted` and have the user refresh `status` page. Use server-side refresh (`<meta http-equiv="refresh" content="5">`) rather than JS polling.

---

## 8. HTML templates (no-JS)

### index.html (upload form)

* Use a plain `<form method="post" enctype="multipart/form-data">`.
* Provide form inputs for numeric options (px_to_mm, thickness_mm, margin_px, voxel_pitch, color choice).
* Provide a submit button.

Example form fields (server will validate):

* `file` (type=file)
* `px_to_mm` (number, step=0.001)
* `thickness_mm` (number, step=0.1)
* `margin_px` (integer)
* `voxel_pitch` (number)

### status.html

* Display job id, current status (queued / processing / done / failed).
* If done, show download links for each generated file.
* Use a meta-refresh header to re-check every N seconds if still processing.

### error.html

* Show friendly error message and a link back to index.

---

## 9. File upload & security

* Validate filename and extension. Use `werkzeug.utils.secure_filename`.
* Generate unique filenames (e.g., `jobid_input.png`).
* Limit max upload size via `app.config['MAX_CONTENT_LENGTH']`.
* Do not serve uploaded files directly from `uploads/`; use a controlled `download` route that streams files with `send_file` or `send_from_directory`.

---

## 10. Processing pipeline

Suggested steps (server-side) for a job:

1. Accept and save input image.
2. Convert to greyscale and threshold (Pillow) to binary image for black/white.
3. Extract pixel coordinates of foreground pixels (as in your script).
4. Merge pixel runs into rectangles to reduce boxes.
5. Generate base meshes (`trimesh.creation.box`) and concatenate.
6. Optionally generate inverted mesh.
7. Attempt boolean subtraction using `trimesh.boolean.difference` (try engines). If missing or fails, attempt OpenSCAD subprocess.
8. If all boolean attempts fail, run voxel subtraction (marching cubes) as fallback.
9. Save generated STLs into `outputs/<job_id>/` and mark job done.

Keep logs in `outputs/<job_id>/process.log` for debugging.

---

## 11. Error handling & logs

* Use try/except around heavy processing and write exceptions to `process.log`.
* Return a friendly error page pointing to the log file for advanced users.
* Clean up temporary files after successful run (or keep for a retention period configured in app).

---

## 12. Testing

* Unit tests for image parsing and rectangle merging (pure Python) — easy to test without heavy deps.
* Integration tests that run the Flask test client to POST a small image and check response and that files exist in outputs.

---

## 13. Deployment notes

* CPU/Memory: voxelization and marching cubes are memory-hungry at high resolutions. Use conservative default voxel_pitch (e.g., 1.0 mm) and allow users to choose smaller values at their own risk.
* Concurrency: use a worker queue (e.g., `RQ`, `Celery`) if you expect multiple simultaneous heavy jobs. With no JS, job status polling can be done by meta-refresh.
* Storage: periodically purge `uploads/` and `outputs/` older than a retention period.

---

## 14. Troubleshooting

* `trimesh.boolean` KeyError 'scad': your installed `trimesh` version lacks direct `scad` interface — the app will fallback to running `openscad` subprocess or voxel subtraction.
* `OpenSCAD parser error` or `mesh not closed`: inspect `outputs/<job_id>/` STL files and try repair or use voxel fallback.
* `matrix_to_marching_cubes` TypeError: older trimesh may not accept `origin`; the code should handle both variants and translate accordingly.
* Missing Python packages: `scikit-image` is required for marching cubes. On macOS arm, prefer `conda` or ensure `pip`, `setuptools`, `wheel` are recent.

---

## 15. License

Choose an appropriate license (e.g., MIT) and include a `LICENSE` file in the repo.

---

## Appendix: Example minimal flow (high level)

1. User opens `/` and selects `image + options`, submits form.
2. Server saves file to `uploads/<jobid>/input.png`.
3. Server runs processing, writes outputs to `outputs/<jobid>/`.
4. User is redirected to `/status/<jobid>` and refreshes until job is `done`.
5. User downloads `subtracted_final.stl` via download link.

---

If you'd like, I can now:

* create ready-to-drop Flask `app.py` + `templates/` files (all server-side, no JS), or
* generate the `README.md` with step-by-step instructions,
* or produce a minimal `index.html` and `status.html` templates you can paste into `templates/`.

Tell me which one you want next.
