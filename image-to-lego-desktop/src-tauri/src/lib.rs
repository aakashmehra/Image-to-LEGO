use std::process::Command;
use std::path::PathBuf;

// Learn more about Tauri commands at https://tauri.app/develop/calling-rust/
#[tauri::command]
fn convert_image(
    image_path: String,
    output_path: String,
    mode: String,
    studs: String,
    ring: String,
    width: f64,
    height: f64,
    thickness: f64,
) -> Result<String, String> {
    let (program, script_arg) = resolve_converter()?;

    let mut cmd = Command::new(&program);
    if let Some(script) = script_arg {
        cmd.arg(&script);
    }
    cmd.arg("--input").arg(&image_path)
       .arg("--output").arg(&output_path)
       .arg("--mode").arg(&mode)
       .arg("--studs").arg(&studs)
       .arg("--ring").arg(&ring)
       .arg("--width").arg(width.to_string())
       .arg("--height").arg(height.to_string())
       .arg("--thickness").arg(thickness.to_string());

    let output = cmd.output().map_err(|e| format!("Failed to launch converter: {}", e))?;

    if output.status.success() {
        Ok(String::from_utf8_lossy(&output.stdout).to_string())
    } else {
        let stdout = String::from_utf8_lossy(&output.stdout);
        let stderr = String::from_utf8_lossy(&output.stderr);
        Err(format!("Conversion failed:\nSTDOUT: {}\nSTDERR: {}", stdout, stderr))
    }
}

/// Returns (program, optional_script_path).
/// Production: ("path/to/cli_convert", None)
/// Development: ("python3" or "python", Some("path/to/cli_convert.py"))
fn resolve_converter() -> Result<(String, Option<String>), String> {
    // --- Production: bundled sidecar binary next to the executable ---
    if let Ok(exe_path) = std::env::current_exe() {
        if let Some(exe_dir) = exe_path.parent() {
            let bin_name = if cfg!(windows) { "cli_convert.exe" } else { "cli_convert" };
            let sidecar = exe_dir.join(bin_name);
            if sidecar.exists() {
                return Ok((sidecar.to_string_lossy().into_owned(), None));
            }
        }
    }

    // --- Development: find cli_convert.py and run with Python ---
    let py_candidates = [
        PathBuf::from("../../cli_convert.py"), // CWD is src-tauri
        PathBuf::from("../cli_convert.py"),    // CWD is image-to-lego-desktop
        PathBuf::from("./cli_convert.py"),     // CWD is APStudios
    ];

    for p in &py_candidates {
        if p.exists() {
            return find_python().map(|py| (py, Some(p.to_string_lossy().into_owned())));
        }
    }

    // Also check relative to the executable (for `cargo tauri dev`)
    if let Ok(exe_path) = std::env::current_exe() {
        if let Some(exe_dir) = exe_path.parent() {
            for rel in &["../cli_convert.py", "cli_convert.py"] {
                let p = exe_dir.join(rel);
                if p.exists() {
                    return find_python().map(|py| (py, Some(p.to_string_lossy().into_owned())));
                }
            }
        }
    }

    Err("cli_convert not found. In production, ensure the app was built with `npm run tauri build`. In development, ensure cli_convert.py is in the APStudios directory.".to_string())
}

fn find_python() -> Result<String, String> {
    for candidate in &["python3", "python"] {
        if Command::new(candidate).arg("--version").output().is_ok() {
            return Ok(candidate.to_string());
        }
    }
    Err("Python not found in PATH. Please install Python 3.".to_string())
}

#[tauri::command]
fn read_image_base64(path: String) -> Result<String, String> {
    use std::fs::File;
    use std::io::Read;

    let mut file = File::open(&path).map_err(|e| format!("Failed to open image file: {}", e))?;
    let mut buffer = Vec::new();
    file.read_to_end(&mut buffer).map_err(|e| format!("Failed to read image file: {}", e))?;

    let base64_data = base64::Engine::encode(&base64::prelude::BASE64_STANDARD, &buffer);

    let extension = std::path::Path::new(&path)
        .extension()
        .and_then(|ext| ext.to_str())
        .unwrap_or("png")
        .to_lowercase();

    let mime_type = match extension.as_str() {
        "jpg" | "jpeg" => "image/jpeg",
        "gif" => "image/gif",
        "bmp" => "image/bmp",
        "png" => "image/png",
        _ => "image/png",
    };

    Ok(format!("data:{};base64,{}", mime_type, base64_data))
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_opener::init())
        .invoke_handler(tauri::generate_handler![convert_image, read_image_base64])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
