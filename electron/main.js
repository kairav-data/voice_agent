/**
 * ECOWHISPER Desktop Application — Electron Main Process
 * 
 * Features:
 * - Robust lifecycle management of the Python AI / Whisper / Ollama backend
 * - Safe process execution with physical directory isolation (never asar cwd)
 * - Windows 11 frameless glassmorphic window with custom titlebar
 * - System tray with live status indicators and quick toggles
 * - Global push-to-talk hotkeys (Ctrl+Shift+Space) & summon hotkey (Ctrl+Shift+K)
 * - Native desktop notifications and hardware diagnostics
 * - Clean zero-zombie process termination on exit
 */

const {
  app,
  BrowserWindow,
  Tray,
  Menu,
  globalShortcut,
  ipcMain,
  nativeImage,
  Notification,
  shell
} = require('electron');

const path = require('path');
const http = require('http');
const https = require('https');
const { spawn, exec } = require('child_process');
const os = require('os');
const fs = require('fs');

// Ignore self-signed cert errors on localhost loopback for seamless WebRTC / audio streaming
app.commandLine.appendSwitch('ignore-certificate-errors');
app.commandLine.appendSwitch('allow-insecure-localhost', 'true');
app.commandLine.appendSwitch('disable-http-cache');

// Ensure single instance lock
const gotTheLock = app.requestSingleInstanceLock();
if (!gotTheLock) {
  app.quit();
  process.exit(0);
}

let mainWindow = null;
let splashWindow = null;
let tray = null;
let pythonProcess = null;
let isQuitting = false;
let backendSpawnedByElectron = false;
let isPinned = false;

let BACKEND_PROTOCOL = 'http';
let BACKEND_PORT = parseInt(process.env.VA_PORT || process.env.PORT || '8000', 10);
const BACKEND_HOST = '127.0.0.1';
let BACKEND_URL = `${BACKEND_PROTOCOL}://${BACKEND_HOST}:${BACKEND_PORT}`;

// Resolve static assets
const devRootDir = path.resolve(__dirname, '..');
const ICON_PATH = fs.existsSync(path.join(devRootDir, 'assets', 'icon.png'))
  ? path.join(devRootDir, 'assets', 'icon.png')
  : path.join(process.resourcesPath, 'ECOWHISPER', 'assets', 'icon.ico');

const ICO_PATH = fs.existsSync(path.join(devRootDir, 'assets', 'icon.ico'))
  ? path.join(devRootDir, 'assets', 'icon.ico')
  : path.join(process.resourcesPath, 'ECOWHISPER', 'assets', 'icon.ico');

const TRAY_ICON_PATH = fs.existsSync(path.join(devRootDir, 'assets', 'tray.png'))
  ? path.join(devRootDir, 'assets', 'tray.png')
  : (fs.existsSync(path.join(devRootDir, 'assets', 'icon.ico')) ? path.join(devRootDir, 'assets', 'icon.ico') : ICON_PATH);

/**
 * Check if the Python backend is active and healthy on a given protocol and port.
 */
function checkEndpointHealth(protocol, port, timeoutMs = 700) {
  return new Promise((resolve) => {
    const client = protocol === 'https' ? https : http;
    const req = client.get(`${protocol}://${BACKEND_HOST}:${port}/api/status`, {
      timeout: timeoutMs,
      rejectUnauthorized: false
    }, (res) => {
      resolve(res.statusCode >= 200 && res.statusCode < 400);
    });
    req.on('error', () => resolve(false));
    req.on('timeout', () => {
      req.destroy();
      resolve(false);
    });
  });
}

/**
 * Check if the Python backend is active across primary and fallback ports, supporting both HTTP and HTTPS.
 */
async function checkBackendHealth() {
  const portsToCheck = [...new Set([BACKEND_PORT, 8000, 7860])];
  for (const port of portsToCheck) {
    for (const proto of ['http', 'https']) {
      const ok = await checkEndpointHealth(proto, port, 600);
      if (ok) {
        BACKEND_PROTOCOL = proto;
        BACKEND_PORT = port;
        BACKEND_URL = `${proto}://${BACKEND_HOST}:${port}`;
        console.log(`[Electron] Connected to active voice agent at ${BACKEND_URL}`);
        return true;
      }
    }
  }
  return false;
}

/**
 * Locate the appropriate backend executable and its working directory.
 * Crucial: cwd must ALWAYS be a physical filesystem directory, never inside app.asar!
 */
function resolveBackendExecutable() {
  // In development (npm start / run_desktop.bat), ALWAYS run live Python source code directly
  if (!app.isPackaged) {
    const localAppData = process.env.LOCALAPPDATA || path.join(os.homedir(), 'AppData', 'Local');
    const systemPy311 = path.join(localAppData, 'Programs', 'Python', 'Python311', 'python.exe');
    if (fs.existsSync(systemPy311)) {
      console.log(`[Electron Dev] Using configured Python 3.11 with full dependencies: ${systemPy311}`);
      return {
        command: systemPy311,
        args: ['main.py', '--ui', '--port', String(BACKEND_PORT), '--no-auto-open', '--no-ssl'],
        cwd: devRootDir
      };
    }

    const venvPythonWin = path.join(devRootDir, '.venv', 'Scripts', 'python.exe');
    if (fs.existsSync(venvPythonWin)) {
      console.log(`[Electron Dev] Using virtualenv Python: ${venvPythonWin}`);
      return {
        command: venvPythonWin,
        args: ['main.py', '--ui', '--port', String(BACKEND_PORT), '--no-auto-open', '--no-ssl'],
        cwd: devRootDir
      };
    }

    const venvPythonLinux = path.join(devRootDir, '.venv', 'bin', 'python');
    if (fs.existsSync(venvPythonLinux)) {
      console.log(`[Electron Dev] Using virtualenv Python: ${venvPythonLinux}`);
      return {
        command: venvPythonLinux,
        args: ['main.py', '--ui', '--port', String(BACKEND_PORT), '--no-auto-open', '--no-ssl'],
        cwd: devRootDir
      };
    }

    console.log('[Electron Dev] Using system Python for live development');
    return {
      command: 'python',
      args: ['main.py', '--ui', '--port', String(BACKEND_PORT), '--no-auto-open', '--no-ssl'],
      cwd: devRootDir
    };
  }

  // Candidate paths in packaged distribution
  const packagedCandidates = [
    path.join(process.resourcesPath, 'ECOWHISPER', 'ECOWHISPER.exe'),
    path.join(path.dirname(app.getPath('exe')), 'resources', 'ECOWHISPER', 'ECOWHISPER.exe'),
    path.join(path.dirname(app.getPath('exe')), 'ECOWHISPER', 'ECOWHISPER.exe'),
    path.join(devRootDir, 'dist', 'ECOWHISPER', 'ECOWHISPER.exe')
  ];

  for (const candidate of packagedCandidates) {
    if (fs.existsSync(candidate)) {
      const candidateDir = path.dirname(candidate);
      console.log(`[Electron] Found bundled backend at: ${candidate}`);
      console.log(`[Electron] Using backend working directory: ${candidateDir}`);
      return {
        command: candidate,
        args: ['--ui', '--port', String(BACKEND_PORT), '--no-auto-open', '--no-ssl'],
        cwd: candidateDir
      };
    }
  }

  // Development paths fallback
  const venvPythonWin = path.join(devRootDir, '.venv', 'Scripts', 'python.exe');
  if (fs.existsSync(venvPythonWin)) {
    return {
      command: venvPythonWin,
      args: ['main.py', '--ui', '--port', String(BACKEND_PORT), '--no-auto-open', '--no-ssl'],
      cwd: devRootDir
    };
  }

  const venvPythonLinux = path.join(devRootDir, '.venv', 'bin', 'python');
  if (fs.existsSync(venvPythonLinux)) {
    return {
      command: venvPythonLinux,
      args: ['main.py', '--ui', '--port', String(BACKEND_PORT), '--no-auto-open', '--no-ssl'],
      cwd: devRootDir
    };
  }

  // Fallback to system python
  return {
    command: 'python',
    args: ['main.py', '--ui', '--port', String(BACKEND_PORT), '--no-auto-open', '--no-ssl'],
    cwd: devRootDir
  };
}

/**
 * Spawns the Python voice agent backend if not already running.
 */
async function startBackendIfNeeded() {
  const alreadyRunning = await checkBackendHealth();
  if (alreadyRunning) {
    console.log('[Electron] Backend server is already running on port', BACKEND_PORT);
    updateSplashStatus('Connecting to active Voice Engine...', 70);
    return true;
  }

  updateSplashStatus('Starting ECOWHISPER Neural Engine...', 25);
  const target = resolveBackendExecutable();

  if (!target || !target.command) {
    console.error('[Electron] Could not resolve backend executable.');
    updateSplashStatus('Error: Backend executable missing.', 0);
    return false;
  }

  const { command, args, cwd } = target;
  console.log(`[Electron] Launching backend: ${command} ${args.join(' ')}`);
  console.log(`[Electron] Working directory: ${cwd}`);

  try {
    pythonProcess = spawn(command, args, {
      cwd: cwd,
      env: {
        ...process.env,
        PYTHONUNBUFFERED: '1',
        VA_AUTO_OPEN: '0',
        VA_SSL: 'false',
        SSL: 'false',
        VA_PORT: String(BACKEND_PORT),
        PORT: String(BACKEND_PORT),
      },
      windowsHide: true,
      stdio: ['pipe', 'pipe', 'pipe']
    });

    backendSpawnedByElectron = true;

    // Prevent uncaught exception if process fails to spawn
    pythonProcess.on('error', (err) => {
      console.error('[Electron] Backend process spawn error:', err);
      updateSplashStatus(`Failed to launch backend: ${err.message}`, 0);
    });

    pythonProcess.stdout.on('data', (chunk) => {
      const line = chunk.toString().trim();
      console.log(`[Backend] ${line}`);
      if (line.includes('Faster-Whisper') || line.includes('Ollama')) {
        updateSplashStatus('Loading AI Models...', 50);
      } else if (line.includes('Uvicorn running') || line.includes('Application startup complete') || line.includes('COMMAND CENTER')) {
        updateSplashStatus('Voice Agent Core Ready!', 90);
      }
    });

    pythonProcess.stderr.on('data', (chunk) => {
      console.error(`[Backend ERR] ${chunk.toString().trim()}`);
    });

    pythonProcess.on('exit', (code, signal) => {
      console.log(`[Electron] Backend exited with code ${code}, signal ${signal}`);
      pythonProcess = null;
      if (!isQuitting && mainWindow && !mainWindow.isDestroyed()) {
        mainWindow.webContents.send('backend:terminated', { code, signal });
      }
    });

    // Poll until backend responds (up to 30 seconds for initial cold boot)
    const maxAttempts = 50;
    for (let i = 1; i <= maxAttempts; i++) {
      await new Promise((r) => setTimeout(r, 600));
      updateSplashStatus('Synchronizing neural audio pipeline...', 30 + Math.min(60, i * 1.5));
      const healthy = await checkBackendHealth();
      if (healthy) {
        console.log(`[Electron] Backend healthy on port ${BACKEND_PORT} after attempt ${i}`);
        updateSplashStatus('Initializing Desktop Command Center...', 98);
        return true;
      }
    }

    console.warn('[Electron] Backend health check timed out.');
    return false;
  } catch (err) {
    console.error('[Electron] Exception while spawning backend:', err);
    updateSplashStatus(`Error: ${err.message}`, 0);
    return false;
  }
}

/**
 * Creates the initial futuristic splash screen.
 */
function createSplashWindow() {
  const icon = fs.existsSync(ICON_PATH) ? ICON_PATH : ICO_PATH;
  splashWindow = new BrowserWindow({
    width: 480,
    height: 380,
    frame: false,
    transparent: true,
    alwaysOnTop: true,
    resizable: false,
    center: true,
    show: false,
    icon: fs.existsSync(icon) ? icon : undefined,
    webPreferences: {
      nodeIntegration: true,
      contextIsolation: false
    }
  });

  splashWindow.loadFile(path.join(__dirname, 'splash.html'));
  splashWindow.once('ready-to-show', () => {
    splashWindow.show();
  });
}

function updateSplashStatus(message, progress) {
  if (splashWindow && !splashWindow.isDestroyed()) {
    splashWindow.webContents.send('splash:status', { message, progress });
  }
}

/**
 * Creates the primary application window.
 */
function createMainWindow() {
  const icon = fs.existsSync(ICON_PATH) ? ICON_PATH : ICO_PATH;
  mainWindow = new BrowserWindow({
    width: 1360,
    height: 880,
    minWidth: 960,
    minHeight: 700,
    frame: false, // Frameless for modern custom titlebar
    transparent: false,
    backgroundColor: '#07090e',
    show: false,
    icon: fs.existsSync(icon) ? icon : undefined,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false,
      webSecurity: false, // Allows local WebRTC/audio streams
      backgroundThrottling: false // Prevents mic/TTS throttling when unfocused
    }
  });

  // Track maximize state to notify custom titlebar
  mainWindow.on('maximize', () => {
    mainWindow.webContents.send('window:maximizeChanged', true);
  });

  mainWindow.on('unmaximize', () => {
    mainWindow.webContents.send('window:maximizeChanged', false);
  });

  const appUrl = `${BACKEND_URL}/?desktop=1`;

  // Gracefully handle connection retry to prevent black screens
  mainWindow.webContents.on('did-fail-load', (_event, errorCode, errorDescription) => {
    console.warn(`[Electron] Page load pending (${errorCode}: ${errorDescription}). Retrying in 1s...`);
    setTimeout(async () => {
      const isUp = await checkBackendHealth();
      if (isUp && mainWindow && !mainWindow.isDestroyed()) {
        mainWindow.loadURL(`${BACKEND_URL}/?desktop=1`);
      }
    }, 1000);
  });

  // Developer hotkeys (Ctrl+R / F5 reload, Ctrl+Shift+I toggle DevTools)
  mainWindow.webContents.on('before-input-event', (event, input) => {
    if ((input.control && input.key.toLowerCase() === 'r') || input.key === 'F5') {
      mainWindow.webContents.session.clearCache().then(() => {
        mainWindow.reload();
      });
      event.preventDefault();
    } else if (input.control && input.shift && input.key.toLowerCase() === 'i') {
      mainWindow.webContents.toggleDevTools();
      event.preventDefault();
    }
  });

  // Purge memory and HTTP cache on load to guarantee latest UI
  mainWindow.webContents.session.clearCache();

  mainWindow.loadURL(`${BACKEND_URL}/?desktop=1`, {
    extraHeaders: 'pragma: no-cache\ncache-control: no-cache'
  });

  mainWindow.webContents.once('did-finish-load', () => {
    setTimeout(() => {
      if (splashWindow && !splashWindow.isDestroyed()) {
        splashWindow.destroy();
        splashWindow = null;
      }
      mainWindow.show();
      mainWindow.focus();
    }, 300);
  });

  // Open external links in user's default browser
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: 'deny' };
  });
}

/**
 * Configures the Windows Taskbar System Tray.
 */
function createTray() {
  try {
    const candidatePaths = [
      path.join(process.resourcesPath, 'ECOWHISPER', 'assets', 'icon.ico'),
      path.join(devRootDir, 'assets', 'icon.ico'),
      path.join(devRootDir, 'assets', 'tray.png'),
      path.join(devRootDir, 'assets', 'icon.png')
    ];
    let trayIcon = null;
    for (const p of candidatePaths) {
      if (fs.existsSync(p)) {
        try {
          const buf = fs.readFileSync(p);
          const img = nativeImage.createFromBuffer(buf);
          if (!img.isEmpty()) {
            trayIcon = img;
            break;
          }
        } catch (e) {}
      }
    }

    if (!trayIcon || trayIcon.isEmpty()) {
      console.warn('[Electron] Tray icon asset unavailable, skipping tray initialization.');
      return () => {};
    }

    tray = new Tray(trayIcon.resize({ width: 16, height: 16 }));
    tray.setToolTip('ECOWHISPER — Autonomous AI Voice Assistant');

  const updateMenu = (statusText = 'Ready') => {
    const contextMenu = Menu.buildFromTemplate([
      { label: `ECOWHISPER: ${statusText}`, enabled: false },
      { type: 'separator' },
      {
        label: 'Show / Focus Window',
        click: () => {
          if (mainWindow) {
            mainWindow.show();
            mainWindow.focus();
          }
        }
      },
      {
        label: 'Push to Talk (Trigger Voice)',
        accelerator: 'Ctrl+Shift+Space',
        click: () => {
          if (mainWindow) mainWindow.webContents.send('global:ptt');
        }
      },
      {
        label: 'Mute / Unmute Microphone',
        accelerator: 'Ctrl+Shift+M',
        click: () => {
          if (mainWindow) mainWindow.webContents.send('global:mute');
        }
      },
      { type: 'separator' },
      {
        label: 'Always on Top',
        type: 'checkbox',
        checked: isPinned,
        click: (item) => {
          isPinned = item.checked;
          if (mainWindow) mainWindow.setAlwaysOnTop(isPinned);
        }
      },
      {
        label: 'Launch at System Startup',
        type: 'checkbox',
        checked: app.getLoginItemSettings().openAtLogin,
        click: (item) => {
          app.setLoginItemSettings({ openAtLogin: item.checked });
        }
      },
      { type: 'separator' },
      {
        label: 'Quit ECOWHISPER',
        click: () => {
          isQuitting = true;
          app.quit();
        }
      }
    ]);
    tray.setContextMenu(contextMenu);
  };

  updateMenu();

  tray.on('click', () => {
    if (mainWindow) {
      if (mainWindow.isVisible()) {
        mainWindow.focus();
      } else {
        mainWindow.show();
      }
    }
  });

    return updateMenu;
  } catch (err) {
    console.error('[Electron] Error initializing tray:', err);
    return () => {};
  }
}

/**
 * Registers global keyboard shortcuts for seamless multitasking.
 */
function registerGlobalShortcuts() {
  // Push-to-Talk from any app
  globalShortcut.register('CommandOrControl+Shift+Space', () => {
    if (mainWindow) {
      mainWindow.webContents.send('global:ptt');
    }
  });

  // Summon/Focus ECOWHISPER
  globalShortcut.register('CommandOrControl+Shift+K', () => {
    if (mainWindow) {
      if (mainWindow.isMinimized()) mainWindow.restore();
      mainWindow.show();
      mainWindow.focus();
    }
  });

  // Global Mic Mute
  globalShortcut.register('CommandOrControl+Shift+M', () => {
    if (mainWindow) {
      mainWindow.webContents.send('global:mute');
    }
  });
}

/**
 * Register IPC handlers for renderer communication.
 */
function setupIpcHandlers(updateTrayMenu) {
  ipcMain.handle('window:minimize', () => {
    if (mainWindow) mainWindow.minimize();
  });

  ipcMain.handle('window:maximize', () => {
    if (mainWindow) {
      if (mainWindow.isMaximized()) {
        mainWindow.unmaximize();
      } else {
        mainWindow.maximize();
      }
      return mainWindow.isMaximized();
    }
    return false;
  });

  ipcMain.handle('window:close', () => {
    if (mainWindow) mainWindow.close();
  });

  ipcMain.handle('window:isMaximized', () => {
    return mainWindow ? mainWindow.isMaximized() : false;
  });

  ipcMain.handle('window:togglePin', () => {
    if (mainWindow) {
      isPinned = !mainWindow.isAlwaysOnTop();
      mainWindow.setAlwaysOnTop(isPinned);
      return isPinned;
    }
    return false;
  });

  ipcMain.handle('window:isPinned', () => {
    return mainWindow ? mainWindow.isAlwaysOnTop() : false;
  });

  ipcMain.handle('notification:send', (_event, { title, body, icon }) => {
    if (Notification.isSupported()) {
      new Notification({
        title: title || 'ECOWHISPER',
        body: body || '',
        icon: icon || (fs.existsSync(ICON_PATH) ? ICON_PATH : undefined),
      }).show();
      return true;
    }
    return false;
  });

  ipcMain.handle('system:specs', () => {
    return {
      platform: os.platform(),
      arch: os.arch(),
      totalMem: Math.round(os.totalmem() / (1024 * 1024)),
      freeMem: Math.round(os.freemem() / (1024 * 1024)),
      cpuModel: os.cpus()[0]?.model || 'Standard CPU',
      cpuCores: os.cpus().length,
      hostname: os.hostname(),
    };
  });

  ipcMain.handle('tray:update', (_event, status) => {
    if (updateTrayMenu) updateTrayMenu(status);
  });

  ipcMain.handle('shell:openExternal', (_event, url) => {
    if (url && (url.startsWith('http://') || url.startsWith('https://'))) {
      shell.openExternal(url);
    }
  });
}

/**
 * Cleanly kills any backend child processes when quitting.
 */
function terminateBackend() {
  if (backendSpawnedByElectron && pythonProcess && pythonProcess.pid) {
    console.log(`[Electron] Terminating backend process PID ${pythonProcess.pid}...`);
    try {
      if (process.platform === 'win32') {
        exec(`taskkill /pid ${pythonProcess.pid} /T /F`);
      } else {
        process.kill(-pythonProcess.pid, 'SIGKILL');
      }
    } catch (e) {
      console.error('[Electron] Error during backend termination:', e);
    }
    pythonProcess = null;
  }
}

// App lifecycle
app.on('second-instance', () => {
  if (mainWindow) {
    if (mainWindow.isMinimized()) mainWindow.restore();
    mainWindow.show();
    mainWindow.focus();
  }
});

app.whenReady().then(async () => {
  createSplashWindow();
  const updateTrayMenu = createTray();
  setupIpcHandlers(updateTrayMenu);
  registerGlobalShortcuts();

  const isReady = await startBackendIfNeeded();
  if (!isReady) {
    console.warn('[Electron] Backend took longer than expected, verifying port...');
    await new Promise((r) => setTimeout(r, 2000));
  }

  createMainWindow();

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createMainWindow();
    }
  });
});

app.on('before-quit', () => {
  isQuitting = true;
  globalShortcut.unregisterAll();
  terminateBackend();
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    isQuitting = true;
    terminateBackend();
    app.quit();
  }
});
