use std::process::Command as StdCommand;
use std::sync::Mutex;

use tauri::menu::{Menu, MenuItem};
use tauri::tray::TrayIconBuilder;
use tauri::{Emitter, Manager, RunEvent, State};
use tauri_plugin_shell::{process::CommandChild, ShellExt};

/// Keeps the tray icon alive for the app's lifetime; dropping the handle would
/// remove the icon from the OS tray.
struct TrayHandle(tauri::tray::TrayIcon);

/// The two process types supported by development and packaged builds.
/// Tauri's sidecar returns a `CommandChild`, while the Python development
/// fallback returns a standard `std::process::Child`; wrapping both lets them
/// coexist in one owned value and be terminated identically on exit.
enum BackendChild {
    Sidecar(CommandChild),
    Python(std::process::Child),
}

impl BackendChild {
    fn kill(self) -> std::io::Result<()> {
        match self {
            BackendChild::Sidecar(child) => child
                .kill()
                .map_err(|error| std::io::Error::other(error.to_string())),
            BackendChild::Python(mut child) => {
                let result = child.kill();
                let _ = child.wait();
                result
            }
        }
    }
}

/// The spawned backend process, managed for the app's lifetime so it can be
/// killed on exit (no orphaned Python holding port 5178).
struct BackendProcess(Mutex<Option<BackendChild>>);

impl BackendProcess {
    fn stop(&self) {
        let child = self.0.lock().unwrap().take();
        if let Some(child) = child {
            let _ = child.kill();
        }
    }
}

fn python_script(app: &tauri::AppHandle) -> Option<std::path::PathBuf> {
    let candidates = [
        std::env::current_dir().ok().map(|dir| dir.join("backend/app.py")),
        app.path()
            .resource_dir()
            .ok()
            .map(|dir| dir.join("backend/app.py")),
    ];
    candidates
        .into_iter()
        .flatten()
        .find(|path| path.is_file())
}

fn spawn_backend(app: &tauri::AppHandle) -> Option<BackendChild> {
    let data_dir = app.path().app_data_dir().ok();

    // Preferred in packaged builds: a PyInstaller executable with the target
    // triple suffix expected by Tauri's externalBin configuration.
    let port = std::env::var("YTM_BACKEND_PORT").unwrap_or("5178".into());
    if let Ok(command) = app.shell().sidecar("ytm-backend") {
        let command = command
            .env("YTM_BACKEND_PORT", &port)
            .env("PYTHONUNBUFFERED", "1");
        let command = if let Some(dir) = data_dir.as_ref() {
            command.env("YTM_DATA_DIR", dir)
        } else {
            command
        };
        if let Ok((_events, child)) = command.spawn() {
            return Some(BackendChild::Sidecar(child));
        }
    }

    // Development/source-checkout fallback. In a packaged build this also
    // works when Python and the backend resource are deliberately installed.
    let script = python_script(app)?;
    let mut command = StdCommand::new("python");
    command
        .arg(script.clone())
        .env("YTM_BACKEND_PORT", &port)
        .env("PYTHONUNBUFFERED", "1");
    if let Some(dir) = data_dir {
        command.env("YTM_DATA_DIR", dir);
    }
    if let Some(parent) = script.parent() {
        command.current_dir(parent.parent().unwrap_or(parent));
    }
    command.spawn().ok().map(BackendChild::Python)
}

#[tauri::command]
fn restart_backend(app: tauri::AppHandle, backend: State<'_, BackendProcess>) {
    backend.stop();
    *backend.0.lock().unwrap() = spawn_backend(&app);
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_window_state::Builder::default().build())
        .setup(|app| {
            let child = spawn_backend(app.handle());
            if child.is_none() {
                eprintln!("[ytm-player] Could not start the backend (no sidecar, backend resource, or Python on PATH).");
            }
            app.manage(BackendProcess(Mutex::new(child)));
            // System tray: media actions emit to the webview (which owns the
            // Media Session integration); Show/Hide and Quit act on the window
            // directly. Play/Pause/Next/Previous arrive via the Svelte listener.
            if let Ok(show) = MenuItem::with_id(app, "show", "Show / Hide", true, None::<&str>) {
                if let Ok(play) = MenuItem::with_id(app, "play", "Play / Pause", true, None::<&str>) {
                    if let Ok(next) = MenuItem::with_id(app, "next", "Next Track", true, None::<&str>) {
                        if let Ok(previous) = MenuItem::with_id(app, "previous", "Previous Track", true, None::<&str>) {
                            if let Ok(quit) = MenuItem::with_id(app, "quit", "Quit", true, None::<&str>) {
                                if let Ok(menu) = Menu::with_items(app, &[&play, &next, &previous, &show, &quit]) {
                                    if let Ok(tray) = TrayIconBuilder::with_id("main-tray")
                                        .icon(app.default_window_icon().unwrap().clone())
                                        .menu(&menu)
                                        .show_menu_on_left_click(false)
                                        .on_menu_event(|app, event| match event.id.as_ref() {
                                            "play" => { let _ = app.emit("tray-toggle-play", ()); }
                                            "next" => { let _ = app.emit("tray-next", ()); }
                                            "previous" => { let _ = app.emit("tray-prev", ()); }
                                            "show" => {
                                                if let Some(window) = app.get_webview_window("main") {
                                                    if window.is_visible().unwrap_or(false) {
                                                        let _ = window.hide();
                                                    } else {
                                                        let _ = window.show();
                                                        let _ = window.set_focus();
                                                    }
                                                }
                                            }
                                            "quit" => app.exit(0),
                                            _ => {}
                                        })
                                        .build(app)
                                    {
                                        app.manage(TrayHandle(tray));
                                    }
                                }
                            }
                        }
                    }
                }
            }
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![restart_backend])
        .build(tauri::generate_context!())
        .expect("error while building tauri application")
        .run(|app_handle, event| {
            if matches!(event, RunEvent::Exit) {
                if let Some(backend) = app_handle.try_state::<BackendProcess>() {
                    backend.stop();
                }
            }
        });
}
