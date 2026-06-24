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
    // Resolve the path of the script relative to CWD or executable
    let paths_to_try = [
        PathBuf::from("../../cli_convert.py"), // CWD is src-tauri
        PathBuf::from("../cli_convert.py"),    // CWD is image-to-lego-desktop
        PathBuf::from("./cli_convert.py"),     // CWD is APStudios
    ];
    
    let mut script_path = PathBuf::new();
    for p in &paths_to_try {
        if p.exists() {
            script_path = p.clone();
            break;
        }
    }
    
    if script_path.as_os_str().is_empty() {
        if let Ok(exe_path) = std::env::current_exe() {
            if let Some(exe_dir) = exe_path.parent() {
                let test_path = exe_dir.join("../cli_convert.py");
                if test_path.exists() {
                    script_path = test_path;
                } else {
                    let test_path2 = exe_dir.join("cli_convert.py");
                    if test_path2.exists() {
                        script_path = test_path2;
                    }
                }
            }
        }
    }

    if script_path.as_os_str().is_empty() {
        return Err("cli_convert.py script not found. Make sure the script is adjacent to the project.".to_string());
    }
    
    let script_str = script_path.to_string_lossy().into_owned();
    
    // Try python3 first
    let mut command = Command::new("python3");
    command.arg(&script_str)
           .arg("--input").arg(&image_path)
           .arg("--output").arg(&output_path)
           .arg("--mode").arg(&mode)
           .arg("--studs").arg(&studs)
           .arg("--ring").arg(&ring)
           .arg("--width").arg(width.to_string())
           .arg("--height").arg(height.to_string())
           .arg("--thickness").arg(thickness.to_string());
           
    let output = match command.output() {
        Ok(out) => {
            if out.status.success() {
                out
            } else {
                // If python3 failed, try "python"
                let mut alt_command = Command::new("python");
                alt_command.arg(&script_str)
                           .arg("--input").arg(&image_path)
                           .arg("--output").arg(&output_path)
                           .arg("--mode").arg(&mode)
                           .arg("--studs").arg(&studs)
                           .arg("--ring").arg(&ring)
                           .arg("--width").arg(width.to_string())
                           .arg("--height").arg(height.to_string())
                           .arg("--thickness").arg(thickness.to_string());
                match alt_command.output() {
                    Ok(alt_out) => {
                        if alt_out.status.success() {
                            alt_out
                        } else {
                            let err_msg = String::from_utf8_lossy(&alt_out.stderr).to_string();
                            let out_msg = String::from_utf8_lossy(&alt_out.stdout).to_string();
                            return Err(format!("Python conversion failed:\nSTDOUT: {}\nSTDERR: {}", out_msg, err_msg));
                        }
                    }
                    Err(e) => {
                        let err_msg = String::from_utf8_lossy(&out.stderr).to_string();
                        return Err(format!("Failed to run python3: {}\nFailed to run python: {}", err_msg, e));
                    }
                }
            }
        }
        Err(_) => {
            // Try "python" directly if python3 command failed to execute (e.g. not in PATH)
            let mut alt_command = Command::new("python");
            alt_command.arg(&script_str)
                       .arg("--input").arg(&image_path)
                       .arg("--output").arg(&output_path)
                       .arg("--mode").arg(&mode)
                       .arg("--studs").arg(&studs)
                       .arg("--ring").arg(&ring)
                       .arg("--width").arg(width.to_string())
                       .arg("--height").arg(height.to_string())
                       .arg("--thickness").arg(thickness.to_string());
            match alt_command.output() {
                Ok(alt_out) => {
                    if alt_out.status.success() {
                        alt_out
                    } else {
                        let err_msg = String::from_utf8_lossy(&alt_out.stderr).to_string();
                        let out_msg = String::from_utf8_lossy(&alt_out.stdout).to_string();
                        return Err(format!("Python conversion failed:\nSTDOUT: {}\nSTDERR: {}", out_msg, err_msg));
                    }
                }
                Err(e) => {
                    return Err(format!("Python executable not found. Please verify Python is installed and added to PATH.\nError: {}", e));
                }
            }
        }
    };
    
    let stdout_str = String::from_utf8_lossy(&output.stdout).to_string();
    Ok(stdout_str)
}

#[tauri::command]
fn read_image_base64(path: String) -> Result<String, String> {
    use std::fs::File;
    use std::io::Read;
    
    let mut file = File::open(&path).map_err(|e| format!("Failed to open image file: {}", e))?;
    let mut buffer = Vec::new();
    file.read_to_end(&mut buffer).map_err(|e| format!("Failed to read image file: {}", e))?;
    
    // Base64 encode using the base64 crate
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
