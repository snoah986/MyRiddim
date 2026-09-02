use std::process::{Child, Command};
use std::sync::Mutex;
use tauri::{Manager, State};
use tauri_plugin_shell::ShellExt;

/// The spawned backend process, managed for the app's lifetime so it can be
/// killed on exit (no orphaned python holding port 5178).
struct BackendProcess(Mutex<Option<Child>>);

fn spawn_backend(app: &tauri::AppHandle) -> Option<Child> {
    // 1. Preferred: the bundled sidecar binary (see tauri.conf.json
    //    "externalBin": ["binaries/ytm-backend"] — package backend/app.py with
    //    PyInstaller and drop the exe into src-tauri/binaries/).
    if let Ok(mut command) = app.shell().sidecar("ytm-backend") {
        if let Ok((_events, child)) = command.spawn() {
            return Some(child);
        }
    }
    // 2. Fallback: a system Python running backend/app.py from the project dir
    //    (dev mode, or a source checkout without a packaged sidecar).
    Command::new("python")
        .arg("backend/app.py")
        .spawn()
        .ok()
}

#[tauri::command]
fn restart_backend(app: tauri::AppHandle, backend: State<'_, BackendProcess>) {
    if let Some(mut child) = backend.0.lock().unwrap().take() {
        let _ = child.kill();
    }
    *backend.0.lock().unwrap() = spawn_backend(&app);
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .setup(|app| {
            let child = spawn_backend(app.handle());
            if child.is_none() {
                eprintln!("[ytm-player] Could not start the backend (no sidecar, no python on PATH).");
            }
            app.manage(BackendProcess(Mutex::new(child)));
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![restart_backend])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}