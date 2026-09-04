/**
 * ECOWHISPER Command Center — Application Controller
 * High-performance WebSocket event dispatcher, state manager, and UI binder.
 */

(function () {
  "use strict";

  // Elements
  const stateBadge = document.getElementById("voiceStateBadge");
  const stateBadgeText = document.getElementById("voiceStateText");
  const orbCenterLabel = document.getElementById("orbCenterLabel");
  const orbWrapper = document.getElementById("orbWrapper");
  const userUtterance = document.getElementById("userUtterance");
  const agentResponseBox = document.getElementById("agentResponseBox");
  const agentResponseText = document.getElementById("agentResponseText");

  // Command Runner Console Drawer
  const consoleDrawer = document.getElementById("consoleDrawer");
  const btnOpenConsole = document.getElementById("btnOpenConsole");
  const btnCloseConsole = document.getElementById("btnCloseConsole");
  const btnCopyConsole = document.getElementById("btnCopyConsole");
  const toolTitle = document.getElementById("toolTitle");
  const toolPurpose = document.getElementById("toolPurpose");
  const toolRiskPill = document.getElementById("toolRiskPill");
  const toolStatusBadge = document.getElementById("toolStatusBadge");
  const toolCommandText = document.getElementById("toolCommandText");
  const toolShellTag = document.getElementById("toolShellTag");
  const consoleOutput = document.getElementById("consoleOutput");
  const consoleOutputTimestamp = document.getElementById("consoleOutputTimestamp");

  const btnPushToTalk = document.getElementById("btnPushToTalk");
  const btnStopInterrupt = document.getElementById("btnStopInterrupt");
  const btnToggleContinuous = document.getElementById("btnToggleContinuous");
  const inputPrompt = document.getElementById("inputPrompt");
  const formPrompt = document.getElementById("formPrompt");

  // Modals & Drawers
  const confirmModal = document.getElementById("confirmModal");
  const confirmCmdText = document.getElementById("confirmCmdText");
  const confirmRiskVal = document.getElementById("confirmRiskVal");
  const confirmReversibleVal = document.getElementById("confirmReversibleVal");
  const confirmCategoryVal = document.getElementById("confirmCategoryVal");
  const confirmAffectedVal = document.getElementById("confirmAffectedVal");
  const btnConfirmApprove = document.getElementById("btnConfirmApprove");
  const btnConfirmDecline = document.getElementById("btnConfirmDecline");

  const settingsModal = document.getElementById("settingsModal");
  const btnOpenSettings = document.getElementById("btnOpenSettings");
  const btnCloseSettings = document.getElementById("btnCloseSettings");

  // Theme Management (Light / Luxury White default, with Dark Mode toggle)
  const btnToggleTheme = document.getElementById("btnToggleTheme");
  const themeSunIcon = btnToggleTheme ? btnToggleTheme.querySelector(".theme-icon-sun") : null;
  const themeMoonIcon = btnToggleTheme ? btnToggleTheme.querySelector(".theme-icon-moon") : null;

  function applyTheme(theme) {
    const root = document.documentElement;
    if (theme === "dark") {
      root.setAttribute("data-theme", "dark");
      if (themeSunIcon) themeSunIcon.style.display = "block";
      if (themeMoonIcon) themeMoonIcon.style.display = "none";
      if (btnToggleTheme) btnToggleTheme.setAttribute("title", "Switch to Light Theme");
    } else {
      root.setAttribute("data-theme", "light");
      if (themeSunIcon) themeSunIcon.style.display = "none";
      if (themeMoonIcon) themeMoonIcon.style.display = "block";
      if (btnToggleTheme) btnToggleTheme.setAttribute("title", "Switch to Dark Theme");
    }
    try {
      localStorage.setItem("ecowhisper_theme", theme);
    } catch (e) {}
  }

  let savedTheme = "light";
  try {
    savedTheme = localStorage.getItem("ecowhisper_theme") || localStorage.getItem("voice_agent_theme") || "light";
  } catch (e) {}
  applyTheme(savedTheme);

  if (btnToggleTheme) {
    btnToggleTheme.addEventListener("click", () => {
      const currentTheme = document.documentElement.getAttribute("data-theme") || "light";
      const newTheme = currentTheme === "light" ? "dark" : "light";
      applyTheme(newTheme);
    });
  }

  const historyDrawer = document.getElementById("historyDrawer");
  const btnOpenHistory = document.getElementById("btnOpenHistory");
  const btnCloseHistory = document.getElementById("btnCloseHistory");
  const historyContent = document.getElementById("historyContent");
  const btnClearHistory = document.getElementById("btnClearHistory");

  const timelineDrawer = document.getElementById("timelineDrawer");
  const btnOpenTimeline = document.getElementById("btnOpenTimeline");
  const btnCloseTimeline = document.getElementById("btnCloseTimeline");
  const timelineContent = document.getElementById("timelineContent");

  // Screen Mirror & Mobile Companion
  const btnToggleScreenMirror = document.getElementById("btnToggleScreenMirror");
  const btnOpenMobileConnect = document.getElementById("btnOpenMobileConnect");
  const screenMirrorOverlay = document.getElementById("screenMirrorOverlay");
  const screenStreamVideo = document.getElementById("screenStreamVideo");
  const screenStreamImg = document.getElementById("screenStreamImg");
  const screenLiveBadgeText = document.getElementById("screenLiveBadgeText");
  const btnCloseScreenMirror = document.getElementById("btnCloseScreenMirror");
  const btnScreenFullscreen = document.getElementById("btnScreenFullscreen");
  const btnToggleTouchClicks = document.getElementById("btnToggleTouchClicks");
  const touchClickLabel = document.getElementById("touchClickLabel");
  const screenClickRipple = document.getElementById("screenClickRipple");
  const btnScreenDictate = document.getElementById("btnScreenDictate");
  const screenDictateLabel = document.getElementById("screenDictateLabel");

  const mobileConnectModal = document.getElementById("mobileConnectModal");
  const btnCloseMobileConnect = document.getElementById("btnCloseMobileConnect");
  const mobileQrImg = document.getElementById("mobileQrImg");
  const mobileUrlDisplay = document.getElementById("mobileUrlDisplay");
  const btnCopyMobileUrl = document.getElementById("btnCopyMobileUrl");

  // Mobile Connect Mode Tabs & Remote Tunnel Controls
  const btnTabLocalWifi = document.getElementById("btnTabLocalWifi");
  const btnTabRemoteTunnel = document.getElementById("btnTabRemoteTunnel");
  const paneLocalWifi = document.getElementById("paneLocalWifi");
  const paneRemoteTunnel = document.getElementById("paneRemoteTunnel");
  const remoteTunnelStatusPill = document.getElementById("remoteTunnelStatusPill");
  const remoteTunnelSubtext = document.getElementById("remoteTunnelSubtext");
  const btnToggleTunnel = document.getElementById("btnToggleTunnel");
  const remoteActiveContent = document.getElementById("remoteActiveContent");
  const remoteInactiveContent = document.getElementById("remoteInactiveContent");
  const remoteQrImg = document.getElementById("remoteQrImg");
  const remoteUrlDisplay = document.getElementById("remoteUrlDisplay");
  const btnCopyRemoteUrl = document.getElementById("btnCopyRemoteUrl");

  // Authentication Modal
  const authModal = document.getElementById("authModal");
  const inputAuthToken = document.getElementById("inputAuthToken");
  const btnSubmitAuthToken = document.getElementById("btnSubmitAuthToken");
  const authErrorMsg = document.getElementById("authErrorMsg");

  // Visualizer Bars
  const vizStrip = document.getElementById("visualizerStrip");
  const vizBars = [];
  const NUM_VIZ_BARS = 28;

  for (let i = 0; i < NUM_VIZ_BARS; i++) {
    const bar = document.createElement("div");
    bar.className = "viz-bar";
    vizStrip.appendChild(bar);
    vizBars.push(bar);
  }

  // Device Detection & Audio Routing: Explicit isolation between Phone and Laptop
  const urlParams = new URLSearchParams(window.location.search);
  const paramDevice = (urlParams.get("device") || urlParams.get("client") || "").toLowerCase();
  const isMobileDevice = (paramDevice === "phone" || paramDevice === "mobile")
    ? true
    : (paramDevice === "laptop" || paramDevice === "desktop")
      ? false
      : (/Mobi|Android|iPhone|iPad|iPod/i.test(navigator.userAgent) ||
         (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1));
  const clientDeviceType = isMobileDevice ? "phone" : "laptop";

  // Auth Token Management (pairing key for remote cellular access)
  let rawUrlToken = urlParams.get("token") || urlParams.get("auth") || "";
  let currentAuthToken = rawUrlToken || "";
  try {
    if (!currentAuthToken) {
      currentAuthToken = localStorage.getItem("voice_agent_token") || "";
    } else {
      localStorage.setItem("voice_agent_token", currentAuthToken);
    }
  } catch (e) {}

  // Strip token from browser URL address bar to keep it clean and confidential
  if (rawUrlToken) {
    urlParams.delete("token");
    urlParams.delete("auth");
    const cleanQuery = urlParams.toString() ? '?' + urlParams.toString() : '';
    try {
      window.history.replaceState({}, document.title, window.location.pathname + cleanQuery + window.location.hash);
    } catch (e) {}
  }

  // Authenticated fetch wrapper for REST API calls
  function authFetch(url, options = {}) {
    options = options || {};
    options.headers = options.headers || {};
    if (currentAuthToken) {
      if (options.headers instanceof Headers) {
        options.headers.set("x-auth-token", currentAuthToken);
      } else {
        options.headers["x-auth-token"] = currentAuthToken;
      }
    }
    return fetch(url, options);
  }

  // Audio Cues via Web Audio API
  let audioCtx = null;
  function getAudioContext() {
    if (!audioCtx) {
      audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    }
    return audioCtx;
  }

  function playSoundCue(type) {
    try {
      const ctx = getAudioContext();
      if (ctx.state === "suspended") ctx.resume();
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.connect(gain);
      gain.connect(ctx.destination);

      const now = ctx.currentTime;
      if (type === "listen") {
        osc.type = "sine";
        osc.frequency.setValueAtTime(520, now);
        osc.frequency.exponentialRampToValueAtTime(780, now + 0.1);
        gain.gain.setValueAtTime(0.04, now);
        gain.gain.exponentialRampToValueAtTime(0.001, now + 0.12);
        osc.start(now);
        osc.stop(now + 0.12);
      } else if (type === "done") {
        osc.type = "sine";
        osc.frequency.setValueAtTime(660, now);
        osc.frequency.setValueAtTime(880, now + 0.08);
        gain.gain.setValueAtTime(0.04, now);
        gain.gain.exponentialRampToValueAtTime(0.001, now + 0.2);
        osc.start(now);
        osc.stop(now + 0.2);
      }
    } catch (e) {
      // Audio context might be restricted before user interaction
    }
  }

  // ========================================================================
  // Client Spoken Audio Playback (for phone / remote device speaker)
  // ========================================================================
  let clientAudio = null;
  let lastReplyAudio = null;
  let lastReplyText = "";

  function primeAudioPlayback() {
    if (!clientAudio) {
      clientAudio = new Audio();
    }
    const actx = getAudioContext();
    if (actx && actx.state === "suspended") {
      actx.resume().catch(() => {});
    }
  }

  // Prime audio playback on initial user gesture on mobile
  document.addEventListener("touchstart", primeAudioPlayback, { passive: true, once: true });
  document.addEventListener("click", primeAudioPlayback, { passive: true, once: true });

  function playSpokenReply(audioSrc, fallbackText) {
    if (!audioSrc && !fallbackText) return;
    primeAudioPlayback();

    if (audioSrc) {
      if (currentAuthToken && audioSrc.startsWith("/") && !audioSrc.includes("token=")) {
        audioSrc += (audioSrc.includes("?") ? "&" : "?") + `token=${encodeURIComponent(currentAuthToken)}`;
      }
      lastReplyAudio = audioSrc;
      lastReplyText = fallbackText || "";
      try {
        if (!clientAudio) clientAudio = new Audio();
        clientAudio.pause();
        clientAudio.src = audioSrc;
        clientAudio.currentTime = 0;

        clientAudio.onplay = () => {
          updateState("speaking");
        };
        clientAudio.onended = () => {
          updateState("idle");
        };
        clientAudio.onerror = (e) => {
          console.warn("[Client audio error, falling back to Web Speech]", e);
          speakWithWebSpeech(fallbackText);
        };

        const p = clientAudio.play();
        if (p !== undefined) {
          p.catch((err) => {
            console.warn("[Autoplay error, fallback to Web Speech]", err);
            speakWithWebSpeech(fallbackText);
          });
        }
      } catch (err) {
        console.warn("[Audio element error]", err);
        speakWithWebSpeech(fallbackText);
      }
    } else if (fallbackText) {
      speakWithWebSpeech(fallbackText);
    }
  }

  function speakWithWebSpeech(text) {
    if (!("speechSynthesis" in window) || !text) return;
    try {
      window.speechSynthesis.cancel();
      const u = new SpeechSynthesisUtterance(text);
      u.onstart = () => updateState("speaking");
      u.onend = () => updateState("idle");
      u.onerror = () => updateState("idle");
      window.speechSynthesis.speak(u);
    } catch (e) {
      console.warn("[WebSpeech error]", e);
      updateState("idle");
    }
  }

  // Initialize Voice Orb
  let orb = null;
  window.addEventListener("DOMContentLoaded", () => {
    orb = new VoiceOrb("orbCanvas");
    updateState("idle");
  });

  // State Machine Labels
  const STATE_LABELS = {
    idle: "ECO STANDBY",
    listening: "LISTENING...",
    hearing: "HEARING VOICE",
    processing: "PROCESSING AUDIO",
    thinking: "THINKING...",
    tool: "PREPARING ACTION...",
    confirmation: "AUTHORIZATION REQUIRED",
    executing: "EXECUTING ACTION...",
    speaking: "SPEAKING...",
    success: "ACTION COMPLETE",
    error: "ERROR ENCOUNTERED",
  };

  let currentState = "idle";
  let pendingConfirmId = null;

  function updateState(newState, extra) {
    currentState = newState;
    if (orb) orb.setState(newState);

    // Update State Badge & Dynamic Beacon
    stateBadge.className = `voice-state-badge state-${newState}`;
    stateBadge.style.display = "inline-flex";
    stateBadgeText.textContent = STATE_LABELS[newState] || newState.toUpperCase();

    // Auto-return from success to standby after 2.8s
    if (newState === "success") {
      setTimeout(() => {
        if (currentState === "success") updateState("idle");
      }, 2800);
    }

    // Update Center Label & Mic Button
    const pushToTalkLabel = document.getElementById("pushToTalkLabel");
    if (newState === "listening") {
      if (orbCenterLabel) orbCenterLabel.textContent = "Listening";
      btnPushToTalk.classList.add("active");
      if (pushToTalkLabel) pushToTalkLabel.textContent = isMobileDevice ? "Listening... (Tap to Send)" : "Listening... (Release to Send)";
    } else if (newState === "thinking") {
      if (orbCenterLabel) orbCenterLabel.textContent = "Thinking";
      btnPushToTalk.classList.remove("active");
      if (pushToTalkLabel) pushToTalkLabel.textContent = "Unmute / Talk";
    } else if (newState === "speaking") {
      if (orbCenterLabel) orbCenterLabel.textContent = "Speaking";
      btnPushToTalk.classList.remove("active");
      if (pushToTalkLabel) pushToTalkLabel.textContent = "Unmute / Talk";
    } else {
      if (orbCenterLabel) orbCenterLabel.textContent = "Press to Talk";
      btnPushToTalk.classList.remove("active");
      if (pushToTalkLabel) pushToTalkLabel.textContent = "Unmute / Talk";
    }

    // Toggle Interrupt button visibility during active speech or execution
    if (["speaking", "executing", "thinking", "tool"].includes(newState)) {
      btnStopInterrupt.style.display = "inline-flex";
    } else {
      btnStopInterrupt.style.display = "none";
    }
  }

  // ========================================================================
  // WebSocket Client & Auth Protocol
  // ========================================================================
  let socket = null;
  let reconnectTimer = null;
  let isAuthBlocked = false;

  function showAuthModal(hasError = false) {
    if (!authModal) return;
    authModal.style.display = "flex";
    authModal.classList.add("active");
    if (authErrorMsg) authErrorMsg.style.display = hasError ? "block" : "none";
    if (inputAuthToken) {
      inputAuthToken.value = currentAuthToken || "";
      setTimeout(() => inputAuthToken.focus(), 150);
    }
  }

  function hideAuthModal() {
    if (!authModal) return;
    authModal.style.display = "none";
    authModal.classList.remove("active");
    if (authErrorMsg) authErrorMsg.style.display = "none";
  }

  if (btnSubmitAuthToken && inputAuthToken) {
    const handleAuthSubmit = () => {
      const val = inputAuthToken.value.trim();
      if (!val) return;
      currentAuthToken = val;
      try {
        localStorage.setItem("voice_agent_token", val);
      } catch (e) {}
      isAuthBlocked = false;
      if (authErrorMsg) authErrorMsg.style.display = "none";
      if (socket) {
        try { socket.close(); } catch (e) {}
      }
      connectWebSocket();
    };
    btnSubmitAuthToken.addEventListener("click", handleAuthSubmit);
    inputAuthToken.addEventListener("keydown", (e) => {
      if (e.key === "Enter") handleAuthSubmit();
    });
  }

  function connectWebSocket() {
    if (isAuthBlocked) return;
    const protocol = location.protocol === "https:" ? "wss:" : "ws:";
    let wsUrl = `${protocol}//${location.host}/ws`;
    if (currentAuthToken) {
      wsUrl += `?token=${encodeURIComponent(currentAuthToken)}`;
    }

    socket = new WebSocket(wsUrl);

    socket.onopen = () => {
      console.log(`[ws] Connected to ECOWHISPER Command Center (${clientDeviceType})`);
      if (reconnectTimer) clearTimeout(reconnectTimer);
      isAuthBlocked = false;
      hideAuthModal();
      sendWS("identify", { client_type: clientDeviceType });
    };

    socket.onmessage = (evt) => {
      try {
        const msg = JSON.parse(evt.data);
        handleServerMessage(msg);
      } catch (err) {
        console.error("[ws] Error parsing server message:", err);
      }
    };

    socket.onclose = (evt) => {
      if (evt && evt.code === 4401) {
        console.warn("[ws] Connection rejected (4401 Unauthorized - pairing key required).");
        isAuthBlocked = true;
        showAuthModal(true);
        return;
      }
      console.warn("[ws] Connection lost. Retrying in 2s...");
      reconnectTimer = setTimeout(connectWebSocket, 2000);
    };

    socket.onerror = (err) => {
      console.error("[ws] Error:", err);
    };
  }

  function sendWS(type, data) {
    if (socket && socket.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify({ type, client: clientDeviceType, ...(data || {}) }));
      return true;
    }
    return false;
  }

  function handleServerMessage(msg) {
    const type = msg.type;

    if (type === "init") {
      updateSystemUI(msg.system);
      renderHistory(msg.history);
      renderTimeline(msg.timeline);
      if (msg.state) updateState(msg.state);
      if (msg.network) {
        if (msg.network.url) updateMobileConnectInfo(msg.network.url);
        if (msg.network.auth_token) currentAuthToken = msg.network.auth_token;
        if (msg.network.tunnel) updateTunnelUI(msg.network.tunnel);
      }

    } else if (type === "tunnel_status") {
      if (msg.tunnel) updateTunnelUI(msg.tunnel);

    } else if (type === "state_changed") {
      updateState(msg.state, msg);

    } else if (type === "mic_meter") {
      if (orb) orb.setAudioLevel(msg.level);
      updateVisualizer(msg.level);

    } else if (type === "listen_started") {
      const listenDevice = msg.device || "laptop";
      if (listenDevice === "both" || listenDevice === clientDeviceType) {
        playSoundCue("listen");
      }
      updateState("listening");

    } else if (type === "transcription_result") {
      userUtterance.textContent = `"${msg.text}"`;
    } else if (type === "screen_frame") {
      if (screenMirrorOpen && screenStreamImg) {
        lastWsFrameTime = performance.now();
        screenStreamImg.src = "data:image/jpeg;base64," + msg.data;
        if (screenStreamImg.style.display !== "block") {
          screenStreamImg.style.display = "block";
        }
        if (screenStreamVideo) {
          screenStreamVideo.style.display = "none";
        }
      }

    } else if (type === "web_app_opened") {
      showWebAppOpenedToast(msg.app, msg.url, msg.message);

    } else if (type === "agent_reply") {
      const targetDevice = msg.target_device || (msg.play_on_client ? "phone" : "laptop");
      const isTargetMe = targetDevice === "both" || targetDevice === clientDeviceType;

      // Only play completion audio chime on the device targeted for the response
      if (isTargetMe) {
        playSoundCue("done");
      }

      agentResponseText.textContent = msg.reply;
      agentResponseBox.style.display = "inline-flex";
      if (msg.item) addHistoryItem(msg.item);

      // If YouTube or a web app was opened in this turn, ensure phone shows action button
      if (msg.item && msg.item.tools && msg.item.tools.length > 0) {
        for (const t of msg.item.tools) {
          const tName = t.name || (t.function && t.function.name) || "";
          if (tName === "play_youtube_video" || tName === "open_web_app") {
            let resObj = t.result;
            if (typeof resObj === "string") {
              try { resObj = JSON.parse(resObj); } catch (e) {}
            }
            if (resObj && (resObj.url || resObj.video_id)) {
              const url = resObj.url || `https://www.youtube.com/watch?v=${resObj.video_id}`;
              const title = resObj.query || resObj.app || "YouTube";
              showWebAppOpenedToast(title, url);
              break;
            }
          }
        }
      }

      lastReplyText = msg.reply || "";
      lastReplyAudio = msg.audio || msg.audio_url || null;

      // Strict Audio Isolation:
      // When target is phone/both and THIS client is a phone, play spoken response on phone speaker.
      // The laptop browser NEVER plays automatic reply audio via browser Audio because
      // the laptop speaker/Bluetooth earphone is driven natively by the Python backend via self.speaker.say().
      const shouldPlayOnThisDevice = (clientDeviceType === "phone") && (targetDevice === "phone" || targetDevice === "both");
      if (shouldPlayOnThisDevice && (msg.audio || msg.audio_url || msg.reply)) {
        playSpokenReply(msg.audio || msg.audio_url, msg.reply);
      }

    } else if (type === "tool_executing") {
      showToolCard(msg);

    } else if (type === "tool_completed") {
      completeToolCard(msg);

    } else if (type === "confirm_request") {
      showConfirmationModal(msg);

    } else if (type === "confirm_resolved") {
      hideConfirmationModal();

    } else if (type === "timeline_item") {
      appendTimelineEntry(msg.entry);

    } else if (type === "continuous_changed") {
      updateContinuousUI(msg.enabled);

    } else if (type === "history_cleared") {
      historyContent.innerHTML = '<p style="color: var(--text-muted); text-align: center; margin-top: 40px;">No conversation history.</p>';
      userUtterance.textContent = 'Say "Open VS Code" or click the orb.';
      userUtterance.classList.add("is-placeholder");
      agentResponseBox.style.display = "none";
      toolActionCard.style.display = "none";

    } else if (type === "interrupted") {
      if (clientAudio) {
        try {
          clientAudio.pause();
          clientAudio.currentTime = 0;
        } catch (e) {}
      }
      if (window.speechSynthesis) {
        try {
          window.speechSynthesis.cancel();
        } catch (e) {}
      }
      updateState("idle");
    }
  }

  // Visualizer bar updates
  function updateVisualizer(level) {
    const activeCount = Math.floor(level * NUM_VIZ_BARS);
    vizBars.forEach((bar, idx) => {
      const height = Math.max(4, (idx < activeCount ? (level * 22 * (1 - Math.abs(idx - activeCount / 2) / NUM_VIZ_BARS)) : 4));
      bar.style.height = `${height}px`;
      if (idx < activeCount) {
        bar.classList.add("active");
      } else {
        bar.classList.remove("active");
      }
    });
  }

  // System UI status bar
  function updateSystemUI(sys) {
    if (!sys) return;
    const pModel = document.getElementById("pillModelName");
    if (pModel) pModel.textContent = sys.ollama?.current_model || "Ollama";
    const pWhisper = document.getElementById("pillWhisperName");
    if (pWhisper) pWhisper.textContent = sys.whisper?.model || "Whisper";
    const pVoice = document.getElementById("pillVoiceName");
    if (pVoice) pVoice.textContent = sys.tts?.voice || sys.tts?.backend || "Voice";
    const pShell = document.getElementById("pillShellName");
    if (pShell) pShell.textContent = sys.safety?.default_shell || "PowerShell";

    const pillDev = document.getElementById("pillDeviceName");
    if (pillDev) {
      pillDev.textContent = clientDeviceType === "phone" ? "Phone Audio" : "Laptop Audio";
    }

    updateContinuousUI(sys.continuous_listening);
  }

  function updateContinuousUI(enabled) {
    if (!btnToggleContinuous) return;
    if (enabled) {
      btnToggleContinuous.title = "Continuous Listening: Active";
      btnToggleContinuous.classList.add("active");
    } else {
      btnToggleContinuous.title = "Continuous Listening: Paused";
      btnToggleContinuous.classList.remove("active");
    }
  }

  // Tool Command Execution Handler
  function showToolCard(data) {
    if (btnOpenConsole) {
      btnOpenConsole.classList.add("running");
    }
    const args = data.args || {};
    if (toolTitle) toolTitle.textContent = `${data.name || "run_command"}`;
    if (toolPurpose) toolPurpose.textContent = args.purpose || args.command || "Executing action...";
    if (toolRiskPill) {
      toolRiskPill.style.display = "";
      toolRiskPill.textContent = "RUNNING";
      toolRiskPill.className = "risk-pill medium";
    }
    if (toolStatusBadge) {
      toolStatusBadge.textContent = "Running...";
      toolStatusBadge.className = "tool-status-badge running";
    }
    if (toolCommandText) toolCommandText.textContent = args.command || args.app_name_or_url || args.query || "";
    if (consoleOutputTimestamp) {
      const now = new Date();
      consoleOutputTimestamp.textContent = now.toTimeString().split(" ")[0];
    }
    if (consoleOutput) consoleOutput.textContent = "Starting process...\n";
  }

  function completeToolCard(data) {
    if (btnOpenConsole) {
      btnOpenConsole.classList.remove("running");
    }
    if (toolStatusBadge) {
      toolStatusBadge.textContent = `Completed`;
      toolStatusBadge.className = "tool-status-badge completed";
    }
    if (toolRiskPill) {
      toolRiskPill.style.display = "";
      toolRiskPill.textContent = "SUCCESS";
      toolRiskPill.className = "risk-pill low";
    }
    if (consoleOutputTimestamp) {
      const now = new Date();
      consoleOutputTimestamp.textContent = now.toTimeString().split(" ")[0];
    }

    try {
      const res = JSON.parse(data.result || "{}");
      if (consoleOutput) {
        consoleOutput.innerHTML = "";
        if (res.stdout) {
          const span = document.createElement("span");
          span.textContent = res.stdout;
          consoleOutput.appendChild(span);
        }
        if (res.stderr) {
          const errSpan = document.createElement("span");
          errSpan.className = "stderr";
          errSpan.textContent = (res.stdout ? "\n" : "") + res.stderr;
          consoleOutput.appendChild(errSpan);
        }
        if (!res.stdout && !res.stderr) {
          consoleOutput.textContent = data.result || "(Process exited with code 0. No output.)";
        }
      }
    } catch (e) {
      if (consoleOutput) consoleOutput.textContent = data.result || "(Execution completed)";
    }
  }

  // Safety Confirmation Modal
  function showConfirmationModal(data) {
    pendingConfirmId = data.id;
    confirmCmdText.textContent = data.command || "";
    confirmRiskVal.textContent = (data.risk || "medium").toUpperCase();
    confirmRiskVal.style.color = data.risk === "destructive" || data.risk === "high" ? "var(--accent-rose)" : "var(--accent-amber)";
    confirmReversibleVal.textContent = data.reversible ? "Yes" : "No";
    confirmCategoryVal.textContent = data.category || "Local System";
    confirmAffectedVal.textContent = data.affected || "Local Machine";
    confirmModal.classList.add("active");

    if (clientDeviceType === "phone" && data.audio) {
      playSpokenReply(data.audio, "Confirmation required. May I run that command?");
    }
  }

  function hideConfirmationModal() {
    confirmModal.classList.remove("active");
    pendingConfirmId = null;
  }

  btnConfirmApprove.addEventListener("click", () => {
    if (pendingConfirmId) {
      sendWS("confirm_response", { id: pendingConfirmId, approved: true });
      hideConfirmationModal();
    }
  });

  btnConfirmDecline.addEventListener("click", () => {
    if (pendingConfirmId) {
      sendWS("confirm_response", { id: pendingConfirmId, approved: false });
      hideConfirmationModal();
    }
  });

  // Push to talk & Microphone interaction
  let isTalking = false;
  let talkStartTime = 0;
  let isAltMHeld = false;
  let isCtrlSpaceHeld = false;
  let isTildeHeld = false;
  let isPointerHeld = false;

  function startTalking() {
    if (isTalking) return;
    isTalking = true;
    talkStartTime = Date.now();
    btnPushToTalk.classList.add("active");
    const label = document.getElementById("pushToTalkLabel");
    if (label) label.textContent = "Listening... (Release to Send)";

    if (isMobileDevice) {
      startPhoneRecording();
    } else {
      sendWS("start_listening");
    }
  }

  function stopTalking() {
    if (!isTalking) return;
    isTalking = false;
    btnPushToTalk.classList.remove("active");
    const label = document.getElementById("pushToTalkLabel");
    if (label) label.textContent = "Hold / Tap to Talk";

    if (isMobileDevice) {
      stopPhoneRecording();
    } else {
      sendWS("stop_listening");
    }
  }

  function toggleTalking() {
    if (isTalking) {
      stopTalking();
    } else {
      startTalking();
    }
  }

  // Pointer/Mouse events on Unmute / Talk button: supports BOTH Tap-to-Toggle AND Hold-to-Talk
  btnPushToTalk.addEventListener("pointerdown", (e) => {
    if (e.button !== 0) return; // primary mouse button only
    e.preventDefault();
    isPointerHeld = true;
    if (isTalking) {
      stopTalking();
    } else {
      startTalking();
    }
  });

  btnPushToTalk.addEventListener("pointerup", (e) => {
    if (!isPointerHeld) return;
    isPointerHeld = false;
    const elapsed = Date.now() - talkStartTime;
    // If held for more than 350ms, this was a push-to-talk hold: release to send!
    if (elapsed > 350 && isTalking) {
      stopTalking();
    }
  });

  btnPushToTalk.addEventListener("pointercancel", () => {
    if (isPointerHeld) {
      isPointerHeld = false;
      if (isTalking) stopTalking();
    }
  });

  orbWrapper.addEventListener("click", () => {
    toggleTalking();
  });

  btnStopInterrupt.addEventListener("click", () => {
    isTalking = false;
    isAltMHeld = false;
    isCtrlSpaceHeld = false;
    isTildeHeld = false;
    isPointerHeld = false;
    sendWS("stop");
  });

  btnToggleContinuous.addEventListener("click", () => {
    sendWS("toggle_continuous");
  });

  // Keyboard Shortcuts: Hybrid Push-to-Talk (Hold while speaking) & Press-to-Talk (Tap once to toggle)
  window.addEventListener("keydown", (e) => {
    // 1. Alt + M (Industry standard Zoom/Teams/Meet shortcut)
    if (e.altKey && (e.key.toLowerCase() === "m" || e.code === "KeyM")) {
      e.preventDefault();
      if (e.repeat) return; // Prevent OS auto-repeat while holding!
      if (!isAltMHeld) {
        isAltMHeld = true;
        if (isTalking) {
          stopTalking();
        } else {
          startTalking();
        }
      }
      return;
    }

    // 2. Ctrl + Space (Quick wake shortcut)
    if ((e.ctrlKey || e.metaKey) && (e.code === "Space" || e.key === " ")) {
      e.preventDefault();
      if (e.repeat) return;
      if (!isCtrlSpaceHeld) {
        isCtrlSpaceHeld = true;
        if (isTalking) {
          stopTalking();
        } else {
          startTalking();
        }
      }
      return;
    }

    // 3. Backquote / Tilde (`) - 1-key Gaming / Discord Push-to-Talk (only if not typing)
    if (e.code === "Backquote" && document.activeElement !== inputPrompt) {
      e.preventDefault();
      if (e.repeat) return;
      if (!isTildeHeld) {
        isTildeHeld = true;
        startTalking();
      }
      return;
    }

    // Escape to Dismiss or Interrupt
    if (e.code === "Escape") {
      isTalking = false;
      isAltMHeld = false;
      isCtrlSpaceHeld = false;
      isTildeHeld = false;
      isPointerHeld = false;
      if (screenMirrorOverlay.style.display !== "none") {
        toggleScreenMirror(false);
      } else if (mobileConnectModal.classList.contains("active")) {
        mobileConnectModal.classList.remove("active");
      } else if (confirmModal.classList.contains("active")) {
        btnConfirmDecline.click();
      } else if (settingsModal.classList.contains("active")) {
        settingsModal.classList.remove("active");
      } else if (consoleDrawer && consoleDrawer.classList.contains("open")) {
        toggleConsoleDrawer(false);
      } else if (timelineDrawer && timelineDrawer.classList.contains("open")) {
        toggleTimelineDrawer(false);
      } else if (historyDrawer && historyDrawer.classList.contains("open")) {
        toggleHistoryDrawer(false);
      } else {
        sendWS("stop");
      }
    }

    // Enter in Confirmation Modal
    if (e.code === "Enter" && confirmModal.classList.contains("active")) {
      btnConfirmApprove.click();
    }

    // Ctrl + K to focus prompt
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
      e.preventDefault();
      inputPrompt.focus();
    }

    // Ctrl + J to toggle Command Runner Console
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "j") {
      e.preventDefault();
      toggleConsoleDrawer();
    }

    // Ctrl + L to clear history
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "l") {
      e.preventDefault();
      sendWS("clear_history");
    }

    // Ctrl + M to toggle Live Laptop Screen Mirror
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "m") {
      e.preventDefault();
      toggleScreenMirror();
    }

    // Ctrl + T to toggle Activity Timeline Drawer
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "t") {
      e.preventDefault();
      toggleTimelineDrawer();
    }

    // Ctrl + H to toggle Command History Drawer
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "h") {
      e.preventDefault();
      toggleHistoryDrawer();
    }

    // Ctrl + comma to open settings
    if ((e.ctrlKey || e.metaKey) && e.key === ",") {
      e.preventDefault();
      settingsModal.classList.toggle("active");
    }
  });

  window.addEventListener("keyup", (e) => {
    // Release of Alt + M (either M or Alt released)
    if (isAltMHeld && (e.code === "KeyM" || e.key.toLowerCase() === "m" || e.key === "Alt" || e.code.startsWith("Alt"))) {
      e.preventDefault();
      isAltMHeld = false;
      const elapsed = Date.now() - talkStartTime;
      // If held for > 350ms, this was push-to-talk: release immediately commits audio!
      if (elapsed > 350 && isTalking) {
        stopTalking();
      }
      // If quick tap (< 350ms), stay unmuted in hands-free toggle mode!
      return;
    }

    // Release of Ctrl + Space
    if (isCtrlSpaceHeld && (e.code === "Space" || e.key === " " || e.key === "Control" || e.code.startsWith("Control"))) {
      e.preventDefault();
      isCtrlSpaceHeld = false;
      const elapsed = Date.now() - talkStartTime;
      if (elapsed > 350 && isTalking) {
        stopTalking();
      }
      return;
    }

    // Release of Tilde (`)
    if (isTildeHeld && e.code === "Backquote") {
      e.preventDefault();
      isTildeHeld = false;
      stopTalking();
      return;
    }
  });

  window.addEventListener("blur", () => {
    if (isAltMHeld || isCtrlSpaceHeld || isTildeHeld || isPointerHeld) {
      isAltMHeld = false;
      isCtrlSpaceHeld = false;
      isTildeHeld = false;
      isPointerHeld = false;
      if (isTalking) stopTalking();
    }
  });

  // Text Prompt Submission
  formPrompt.addEventListener("submit", (e) => {
    e.preventDefault();
    const text = inputPrompt.value.trim();
    if (!text) return;
    inputPrompt.value = "";
    userUtterance.textContent = `"${text}"`;
    userUtterance.classList.remove("is-placeholder");
    sendWS("send_text", { text });
  });

  // Starter Chips
  document.querySelectorAll(".starter-chip").forEach((chip) => {
    chip.addEventListener("click", () => {
      const text = chip.getAttribute("data-prompt") || chip.textContent.trim();
      userUtterance.textContent = `"${text}"`;
      userUtterance.classList.remove("is-placeholder");
      sendWS("send_text", { text });
    });
  });

  // ========================================================================
  // Drawer Controllers (Togglable & Hideable)
  // ========================================================================
  function toggleHistoryDrawer(force) {
    const isOpen = typeof force === "boolean" ? force : !historyDrawer.classList.contains("open");
    historyDrawer.classList.toggle("open", isOpen);
    btnOpenHistory.classList.toggle("active", isOpen);
  }

  function toggleTimelineDrawer(force) {
    const isOpen = typeof force === "boolean" ? force : !timelineDrawer.classList.contains("open");
    timelineDrawer.classList.toggle("open", isOpen);
    btnOpenTimeline.classList.toggle("active", isOpen);
  }

  function toggleConsoleDrawer(force) {
    if (!consoleDrawer) return;
    const isOpen = typeof force === "boolean" ? force : !consoleDrawer.classList.contains("open");
    consoleDrawer.classList.toggle("open", isOpen);
    if (btnOpenConsole) btnOpenConsole.classList.toggle("active", isOpen);
    if (isOpen) {
      if (timelineDrawer && timelineDrawer.classList.contains("open")) toggleTimelineDrawer(false);
      if (historyDrawer && historyDrawer.classList.contains("open")) toggleHistoryDrawer(false);
    }
  }

  // History Drawer
  btnOpenHistory.addEventListener("click", (e) => {
    e.stopPropagation();
    toggleHistoryDrawer();
  });
  btnCloseHistory.addEventListener("click", () => toggleHistoryDrawer(false));
  btnClearHistory.addEventListener("click", () => sendWS("clear_history"));

  function renderHistory(items) {
    if (!items || !items.length) {
      historyContent.innerHTML = '<p style="color: var(--text-muted); text-align: center; margin-top: 40px;">No conversation history yet.</p>';
      return;
    }
    historyContent.innerHTML = "";
    items.slice().reverse().forEach(addHistoryItem);
  }

  function addHistoryItem(item) {
    const card = document.createElement("div");
    card.className = "history-item-card";
    card.innerHTML = `
      <div style="font-size: 11px; color: var(--text-muted); margin-bottom: 2px;">${item.time || ""}</div>
      <div class="history-item-req">${item.request}</div>
      <div class="history-item-reply">${item.reply}</div>
    `;
    card.addEventListener("click", () => {
      userUtterance.textContent = `"${item.request}"`;
      userUtterance.classList.remove("is-placeholder");
      agentResponseText.textContent = item.reply;
      agentResponseBox.style.display = "inline-flex";
      toggleHistoryDrawer(false);
    });
    historyContent.prepend(card);
  }

  // Activity Timeline Drawer (Right-Docked)
  btnOpenTimeline.addEventListener("click", (e) => {
    e.stopPropagation();
    toggleTimelineDrawer();
  });
  btnCloseTimeline.addEventListener("click", () => toggleTimelineDrawer(false));

  // Command Runner Console Drawer (Top / Right Header Action)
  if (btnOpenConsole) {
    btnOpenConsole.addEventListener("click", (e) => {
      e.stopPropagation();
      toggleConsoleDrawer();
    });
  }
  if (btnCloseConsole) {
    btnCloseConsole.addEventListener("click", () => toggleConsoleDrawer(false));
  }
  if (btnCopyConsole) {
    btnCopyConsole.addEventListener("click", () => {
      if (consoleOutput) {
        const cmd = toolCommandText ? toolCommandText.textContent : "";
        const out = consoleOutput.innerText || consoleOutput.textContent || "";
        const fullText = (cmd ? `$ ${cmd}\n\n` : "") + out;
        navigator.clipboard?.writeText(fullText).then(() => {
          btnCopyConsole.title = "Copied!";
          setTimeout(() => { btnCopyConsole.title = "Copy Output"; }, 1500);
        }).catch(() => {});
      }
    });
  }

  // Click outside drawer to close
  document.addEventListener("click", (e) => {
    if (consoleDrawer && consoleDrawer.classList.contains("open") && !consoleDrawer.contains(e.target) && btnOpenConsole && !btnOpenConsole.contains(e.target)) {
      toggleConsoleDrawer(false);
    }
    if (timelineDrawer && timelineDrawer.classList.contains("open") && !timelineDrawer.contains(e.target) && !btnOpenTimeline.contains(e.target)) {
      toggleTimelineDrawer(false);
    }
    if (historyDrawer && historyDrawer.classList.contains("open") && !historyDrawer.contains(e.target) && !btnOpenHistory.contains(e.target)) {
      toggleHistoryDrawer(false);
    }
  });

  const btnClearTimeline = document.getElementById("btnClearTimeline");
  if (btnClearTimeline) {
    btnClearTimeline.addEventListener("click", () => {
      timelineContent.innerHTML = '<p style="color: var(--text-muted); text-align: center; margin-top: 40px; font-size: 12px;">Activity stream cleared.</p>';
    });
  }

  function renderTimeline(entries) {
    timelineContent.innerHTML = "";
    (entries || []).forEach(appendTimelineEntry);
  }

  function appendTimelineEntry(entry) {
    const div = document.createElement("div");
    div.className = "timeline-entry";
    div.innerHTML = `
      <div class="timeline-time">${entry.time}</div>
      <div class="timeline-msg">${entry.message}</div>
    `;
    timelineContent.appendChild(div);
    timelineContent.scrollTop = timelineContent.scrollHeight;
  }

  // Settings Modal & Hydration
  btnOpenSettings.addEventListener("click", async () => {
    settingsModal.classList.add("active");
    loadSettingsData();
  });
  btnCloseSettings.addEventListener("click", () => settingsModal.classList.remove("active"));

  async function loadSettingsData() {
    try {
      const [resModels, resVoices, resStatus, resDevices] = await Promise.all([
        authFetch("/api/models").then((r) => r.json()).catch(() => ({})),
        authFetch("/api/voices").then((r) => r.json()).catch(() => ({})),
        authFetch("/api/status").then((r) => r.json()).catch(() => ({})),
        authFetch("/api/devices").then((r) => r.json()).catch(() => ({})),
      ]);

      // Populate models
      const selectModel = document.getElementById("settingModel");
      selectModel.innerHTML = "";
      (resModels.models || []).forEach((m) => {
        const opt = document.createElement("option");
        opt.value = m.name;
        opt.textContent = `${m.name} (${m.parameter_size || "local"})`;
        if (m.name === resStatus.ollama?.current_model) opt.selected = true;
        selectModel.appendChild(opt);
      });

      // Populate voice engines and voices
      const selectBackend = document.getElementById("settingTtsBackend");
      selectBackend.value = resStatus.tts?.backend || "auto";

      const selectVoice = document.getElementById("settingVoice");
      selectVoice.innerHTML = "";
      const defaultOpt = document.createElement("option");
      defaultOpt.value = "";
      defaultOpt.textContent = "Default Voice";
      selectVoice.appendChild(defaultOpt);

      (resStatus.tts?.piper_voices || []).forEach((v) => {
        const opt = document.createElement("option");
        opt.value = v;
        opt.textContent = `Piper: ${v.replace(".onnx", "")}`;
        if (resStatus.tts?.voice && v.includes(resStatus.tts.voice)) opt.selected = true;
        selectVoice.appendChild(opt);
      });

      ["en-US-AvaNeural", "en-US-AndrewNeural", "en-IN-NeerjaNeural", "en-IN-PrabhatNeural"].forEach((ev) => {
        const opt = document.createElement("option");
        opt.value = ev;
        opt.textContent = `Edge: ${ev}`;
        if (resStatus.tts?.voice === ev) opt.selected = true;
        selectVoice.appendChild(opt);
      });

      const selectTarget = document.getElementById("settingSpeakerTarget");
      if (selectTarget) selectTarget.value = resStatus.tts?.speaker_target || "auto";

      document.getElementById("settingRate").value = resStatus.tts?.rate || 185;
      document.getElementById("rateValueDisplay").textContent = `${resStatus.tts?.rate || 185} wpm`;

      // Populate microphone input devices
      const selectMic = document.getElementById("settingMicDevice");
      if (selectMic) {
        selectMic.innerHTML = "";
        const autoOpt = document.createElement("option");
        autoOpt.value = "-1";
        const activeLabel = resDevices.active_name ? ` (Active: ${resDevices.active_name})` : "";
        autoOpt.textContent = `Auto-Detect Bluetooth / Default${activeLabel}`;
        selectMic.appendChild(autoOpt);

        (resDevices.devices || []).forEach((dev) => {
          const opt = document.createElement("option");
          opt.value = dev.index;
          const apiTag = dev.api ? ` [${dev.api}]` : "";
          opt.textContent = `${dev.name}${apiTag} (${dev.channels} in, ${Math.round(dev.samplerate)}Hz)`;
          if (resDevices.current === dev.index) {
            opt.selected = true;
          }
          selectMic.appendChild(opt);
        });

        if (resDevices.current === null || resDevices.current === undefined) {
          autoOpt.selected = true;
        }
      }

      // Populate continuous listening dropdown
      const selectContinuous = document.getElementById("settingContinuousListening");
      if (selectContinuous) {
        selectContinuous.value = resStatus.continuous_listening ? "true" : "false";
      }

      document.getElementById("settingConfirmMode").value = resStatus.safety?.confirm_mode || "terminal";
      document.getElementById("settingShell").value = resStatus.safety?.default_shell || "powershell";
    } catch (e) {
      console.error("[settings] Failed to load settings:", e);
    }
  }

  document.getElementById("settingRate").addEventListener("input", (e) => {
    document.getElementById("rateValueDisplay").textContent = `${e.target.value} wpm`;
  });

  document.getElementById("btnSaveSettings").addEventListener("click", async () => {
    const micVal = document.getElementById("settingMicDevice")?.value;
    const continuousVal = document.getElementById("settingContinuousListening")?.value;

    const payload = {
      model: document.getElementById("settingModel").value,
      tts_backend: document.getElementById("settingTtsBackend").value,
      tts_voice: document.getElementById("settingVoice").value,
      tts_rate: parseInt(document.getElementById("settingRate").value, 10),
      tts_speaker_target: document.getElementById("settingSpeakerTarget")?.value || "auto",
      confirm_mode: document.getElementById("settingConfirmMode").value,
      default_shell: document.getElementById("settingShell").value,
      input_device: (micVal !== undefined && micVal !== null && parseInt(micVal, 10) >= 0) ? parseInt(micVal, 10) : null,
      continuous_listening: continuousVal === "true",
    };

    try {
      await authFetch("/api/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      settingsModal.classList.remove("active");
    } catch (e) {
      alert(`Could not save settings: ${e}`);
    }
  });

  const btnCancelSettings = document.getElementById("btnCancelSettings");
  if (btnCancelSettings) {
    btnCancelSettings.addEventListener("click", () => {
      settingsModal.classList.remove("active");
    });
  }

  // Mic Test Button handler
  const btnTestMic = document.getElementById("btnTestMic");
  const micTestBarWrap = document.getElementById("micTestBarWrap");
  const micTestBar = document.getElementById("micTestBar");
  const micTestLevelText = document.getElementById("micTestLevelText");
  const micTestStatusText = document.getElementById("micTestStatusText");
  let isTestingMic = false;

  if (btnTestMic) {
    btnTestMic.addEventListener("click", async () => {
      if (isTestingMic) return;
      isTestingMic = true;
      btnTestMic.disabled = true;
      if (micTestBarWrap) micTestBarWrap.style.display = "block";
      if (micTestStatusText) micTestStatusText.textContent = "Listening to mic (say something now)...";
      if (micTestBar) micTestBar.style.width = "15%";

      const selectedDev = document.getElementById("settingMicDevice")?.value;
      const devPayload = (selectedDev !== undefined && selectedDev !== null && parseInt(selectedDev, 10) >= 0)
        ? { device: parseInt(selectedDev, 10) }
        : {};

      try {
        const res = await authFetch("/api/test-mic", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(devPayload),
        });
        const data = await res.json();
        if (data.success) {
          const pct = Math.min(100, Math.max(5, Math.round(data.peak * 120)));
          if (micTestBar) micTestBar.style.width = `${pct}%`;
          if (micTestLevelText) micTestLevelText.textContent = `${pct}% peak`;
          if (micTestStatusText) micTestStatusText.textContent = `Signal detected from: ${data.device_name}`;
        } else {
          if (micTestStatusText) micTestStatusText.textContent = `Mic test failed: ${data.error || "Unknown"}`;
        }
      } catch (err) {
        if (micTestStatusText) micTestStatusText.textContent = `Mic test error: ${err.message}`;
      } finally {
        setTimeout(() => {
          isTestingMic = false;
          btnTestMic.disabled = false;
        }, 800);
      }
    });
  }

  document.getElementById("btnTestVoice").addEventListener("click", async () => {
    const voice = document.getElementById("settingVoice").value;
    const backend = document.getElementById("settingTtsBackend").value;
    const res = await authFetch("/api/test-voice", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ voice, backend, client: clientDeviceType }),
    });
    try {
      const data = await res.json();
      if (data.audio && clientDeviceType === "phone") {
        playSpokenReply(data.audio, "Voice test preview");
      }
    } catch (e) {}
  });

  // Read response aloud again (routes to local laptop hardware or phone speaker)
  document.getElementById("btnReplayResponse").addEventListener("click", () => {
    const text = agentResponseText.textContent;
    if (clientDeviceType === "phone") {
      if (lastReplyAudio) {
        playSpokenReply(lastReplyAudio, text);
      } else if (text) {
        playSpokenReply(`/api/tts/speak?text=${encodeURIComponent(text)}`, text);
      }
    } else {
      // Laptop: trigger native server-side speaker (OnePlus Bullets / laptop output)
      authFetch("/api/tts/speak-local", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text }),
      }).catch(() => {
        if (lastReplyAudio) playSpokenReply(lastReplyAudio, text);
        else if (text) playSpokenReply(`/api/tts/speak?text=${encodeURIComponent(text)}`, text);
      });
    }
  });

  // Copy response text
  document.getElementById("btnCopyResponse").addEventListener("click", () => {
    const text = agentResponseText.textContent;
    if (text) {
      navigator.clipboard.writeText(text);
      alert("Response copied to clipboard");
    }
  });

  // ========================================================================
  // Live 60 FPS WebRTC Screen Mirror & Audio Controller (Zero-Trim & Pinch-Zoom)
  // ========================================================================
  let screenMirrorOpen = false;
  let touchClicksEnabled = true;
  let rtcPeerConnection = null;
  let rtcDataChannel = null;
  let rtcMicStream = null;
  let screenMicLive = false; // Muted by default!

  // Screen Zoom & Pan State
  let currentZoom = 1.0;
  let panX = 0;
  let panY = 0;
  let isDraggingScreen = false;
  let startTouchX = 0;
  let startTouchY = 0;
  let initialPinchDistance = 0;
  let initialZoom = 1.0;
  let lastTapTime = 0;

  const screenTransformBox = document.getElementById("screenTransformBox");
  const screenZoomToast = document.getElementById("screenZoomToast");
  const btnToggleScreenMic = document.getElementById("btnToggleScreenMic");
  const screenMicLabel = document.getElementById("screenMicLabel");
  const btnToggleScreenFit = document.getElementById("btnToggleScreenFit");
  const screenFitLabel = document.getElementById("screenFitLabel");

  function applyScreenTransform(animate = false) {
    if (!screenTransformBox) return;
    const maxPanX = Math.max(0, ((currentZoom - 1) * window.innerWidth) / 2);
    const maxPanY = Math.max(0, ((currentZoom - 1) * window.innerHeight) / 2);
    panX = Math.max(-maxPanX, Math.min(maxPanX, panX));
    panY = Math.max(-maxPanY, Math.min(maxPanY, panY));

    screenTransformBox.style.transition = animate ? "transform 0.22s cubic-bezier(0.16, 1, 0.3, 1)" : "none";
    screenTransformBox.style.transform = `translate(${panX}px, ${panY}px) scale(${currentZoom})`;
  }

  function showZoomToast(text) {
    if (!screenZoomToast) return;
    screenZoomToast.textContent = text;
    screenZoomToast.classList.add("show");
    clearTimeout(screenZoomToast._timer);
    screenZoomToast._timer = setTimeout(() => {
      screenZoomToast.classList.remove("show");
    }, 1800);
  }

  function setScreenZoom(newZoom, centerX, centerY, animate = true) {
    const clampedZoom = Math.max(1.0, Math.min(3.5, newZoom));
    if (clampedZoom === 1.0) {
      panX = 0;
      panY = 0;
    } else if (centerX !== undefined && centerY !== undefined) {
      const zoomDelta = clampedZoom - currentZoom;
      panX -= (centerX - window.innerWidth / 2) * (zoomDelta / currentZoom) * 0.4;
      panY -= (centerY - window.innerHeight / 2) * (zoomDelta / currentZoom) * 0.4;
    }
    currentZoom = clampedZoom;
    applyScreenTransform(animate);
    if (screenFitLabel) {
      screenFitLabel.textContent = currentZoom > 1.05 ? `${Math.round(currentZoom * 100)}%` : "Fit";
    }
    showZoomToast(`${Math.round(currentZoom * 100)}% View • ${currentZoom > 1.0 ? "Drag to Pan" : "Pinch to Zoom"}`);
  }

  async function updateScreenMicState(wantLive) {
    screenMicLive = wantLive;
    if (wantLive) {
      try {
        if (!rtcMicStream) {
          rtcMicStream = await navigator.mediaDevices.getUserMedia({
            audio: {
              echoCancellation: true,
              noiseSuppression: true,
              autoGainControl: true,
            },
          });
          if (rtcPeerConnection) {
            rtcMicStream.getAudioTracks().forEach((track) => {
              rtcPeerConnection.addTrack(track, rtcMicStream);
            });
          }
        } else {
          rtcMicStream.getAudioTracks().forEach((t) => (t.enabled = true));
        }
        if (btnToggleScreenMic) {
          btnToggleScreenMic.classList.add("active");
          if (screenMicLabel) screenMicLabel.textContent = "Mic: LIVE";
        }
      } catch (err) {
        console.warn("[Screen Mic error]", err);
        screenMicLive = false;
        if (btnToggleScreenMic) {
          btnToggleScreenMic.classList.remove("active");
          if (screenMicLabel) screenMicLabel.textContent = "Mic: OFF";
        }
      }
    } else {
      if (rtcMicStream) {
        rtcMicStream.getAudioTracks().forEach((t) => (t.enabled = false));
      }
      if (btnToggleScreenMic) {
        btnToggleScreenMic.classList.remove("active");
        if (screenMicLabel) screenMicLabel.textContent = "Mic: OFF";
      }
    }
  }

  if (btnToggleScreenMic) {
    btnToggleScreenMic.addEventListener("click", () => {
      updateScreenMicState(!screenMicLive);
    });
  }

  if (btnToggleScreenFit) {
    btnToggleScreenFit.addEventListener("click", () => {
      if (currentZoom < 1.25) {
        setScreenZoom(1.65);
      } else if (currentZoom < 2.0) {
        setScreenZoom(2.5);
      } else {
        setScreenZoom(1.0);
      }
    });
  }

  const btnScreenScrollUp = document.getElementById("btnScreenScrollUp");
  if (btnScreenScrollUp) {
    btnScreenScrollUp.addEventListener("click", () => {
      sendWS("scroll", { direction: "up", amount: "medium" });
    });
  }

  const btnScreenScrollDown = document.getElementById("btnScreenScrollDown");
  if (btnScreenScrollDown) {
    btnScreenScrollDown.addEventListener("click", () => {
      sendWS("scroll", { direction: "down", amount: "medium" });
    });
  }

  const btnScreenPlayPause = document.getElementById("btnScreenPlayPause");
  if (btnScreenPlayPause) {
    btnScreenPlayPause.addEventListener("click", () => {
      sendWS("media_control", { action: "play_pause" });
    });
  }

  let webRtcWatchdog = null;
  let httpFrameLoopActive = false;
  let currentBlobUrl = null;
  let lastWsFrameTime = 0;

  async function startHttpFrameLoop() {
    if (httpFrameLoopActive) return;
    httpFrameLoopActive = true;

    while (screenMirrorOpen && httpFrameLoopActive) {
      // If fresh WebSocket frames are already arriving, yield to WebSocket
      if (performance.now() - lastWsFrameTime < 1200) {
        await new Promise((r) => setTimeout(r, 350));
        continue;
      }

      try {
        const tokenParam = currentAuthToken ? `&token=${encodeURIComponent(currentAuthToken)}` : "";
        const res = await authFetch(`/api/screen/frame?quality=55&scale=0.65${tokenParam}&t=${Date.now()}`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const blob = await res.blob();
        if (!screenMirrorOpen || !httpFrameLoopActive) break;

        const newUrl = URL.createObjectURL(blob);
        if (screenStreamImg) {
          screenStreamImg.src = newUrl;
          if (screenStreamImg.style.display !== "block") {
            screenStreamImg.style.display = "block";
          }
          if (screenStreamVideo) {
            screenStreamVideo.style.display = "none";
          }
        }
        if (currentBlobUrl) {
          URL.revokeObjectURL(currentBlobUrl);
        }
        currentBlobUrl = newUrl;
      } catch (err) {
        console.warn("[HTTP Screen Frame Error]", err);
      }
      await new Promise((r) => setTimeout(r, 100));
    }

    httpFrameLoopActive = false;
    if (currentBlobUrl) {
      URL.revokeObjectURL(currentBlobUrl);
      currentBlobUrl = null;
    }
  }

  function stopHttpFrameLoop() {
    httpFrameLoopActive = false;
    if (currentBlobUrl) {
      URL.revokeObjectURL(currentBlobUrl);
      currentBlobUrl = null;
    }
  }

  function activateStreamFallback() {
    if (webRtcWatchdog) clearTimeout(webRtcWatchdog);
    if (rtcPeerConnection) {
      try {
        rtcPeerConnection.close();
      } catch (e) {}
      rtcPeerConnection = null;
    }
    if (screenStreamVideo) {
      screenStreamVideo.style.display = "none";
      if (screenStreamVideo.srcObject) {
        try {
          screenStreamVideo.srcObject.getTracks().forEach((t) => t.stop());
        } catch (e) {}
        screenStreamVideo.srcObject = null;
      }
    }
    if (screenStreamImg) {
      screenStreamImg.style.display = "block";
    }
    if (screenLiveBadgeText) {
      screenLiveBadgeText.textContent = "LIVE HD (Remote)";
    }

    // 1. Request real-time WebSocket screen frames (instant, works on iOS/Android over tunnel)
    sendWS("start_screen_stream", { fps: 15, quality: 55, scale: 0.65 });

    // 2. Also start HTTP frame polling as automatic fail-safe
    startHttpFrameLoop();
  }

  async function startWebRTCScreen() {
    try {
      if (webRtcWatchdog) clearTimeout(webRtcWatchdog);
      if (rtcPeerConnection) {
        rtcPeerConnection.close();
        rtcPeerConnection = null;
      }

      // Reset Zoom & Pan
      currentZoom = 1.0;
      panX = 0;
      panY = 0;
      applyScreenTransform(false);
      if (screenFitLabel) screenFitLabel.textContent = "Fit";

      // Ensure Mic is MUTED by default when starting
      updateScreenMicState(false);

      // Detect remote tunnel (Cloudflare tunnel, ngrok, localtunnel, etc.)
      // or remote public WAN where WebRTC UDP cannot connect without TURN
      const host = window.location.hostname.toLowerCase();
      const isTunnel = host.includes("trycloudflare.com") || host.includes("loca.lt") || host.includes("ngrok") || host.includes("pagekite");
      const isPublicWan = host !== "localhost" && host !== "127.0.0.1" && !host.startsWith("192.168.") && !host.startsWith("10.") && !host.startsWith("172.");

      if (isTunnel || isPublicWan) {
        console.log("[Screen Mirror] Remote tunnel/cellular detected -> Activating high-speed MJPEG screen stream directly");
        activateStreamFallback();
        return;
      }

      if (screenLiveBadgeText) {
        screenLiveBadgeText.textContent = "60 FPS (LAN)";
      }

      // Local network: attempt ultra-low-latency 60 FPS WebRTC first
      webRtcWatchdog = setTimeout(() => {
        if (screenStreamVideo && (!screenStreamVideo.srcObject || screenStreamVideo.paused)) {
          console.warn("[WebRTC watchdog timeout, activating stream fallback]");
          activateStreamFallback();
        }
      }, 2500);

      rtcPeerConnection = new RTCPeerConnection({
        iceServers: [{ urls: "stun:stun.l.google.com:19302" }],
      });

      // DataChannel for zero-latency touch clicks
      rtcDataChannel = rtcPeerConnection.createDataChannel("input");

      // Add transceiver to receive 60 FPS video
      rtcPeerConnection.addTransceiver("video", { direction: "recvonly" });

      rtcPeerConnection.ontrack = (event) => {
        if (event.track.kind === "video" && screenStreamVideo) {
          if (webRtcWatchdog) clearTimeout(webRtcWatchdog);
          screenStreamVideo.srcObject = event.streams[0];
          screenStreamVideo.style.display = "block";
          if (screenStreamImg) {
            screenStreamImg.style.display = "none";
            screenStreamImg.src = "";
          }
          if (screenLiveBadgeText) {
            screenLiveBadgeText.textContent = "60 FPS WebRTC";
          }
          screenStreamVideo.play().catch(() => {});
        }
      };

      rtcPeerConnection.onconnectionstatechange = () => {
        const s = rtcPeerConnection ? rtcPeerConnection.connectionState : "closed";
        if (s === "failed" || s === "disconnected") {
          console.warn("[WebRTC connection state failed, activating stream fallback]");
          activateStreamFallback();
        }
      };

      rtcPeerConnection.oniceconnectionstatechange = () => {
        const is = rtcPeerConnection ? rtcPeerConnection.iceConnectionState : "closed";
        if (is === "failed" || is === "disconnected") {
          activateStreamFallback();
        }
      };

      const offer = await rtcPeerConnection.createOffer();
      await rtcPeerConnection.setLocalDescription(offer);

      const res = await authFetch("/api/webrtc/offer", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          sdp: rtcPeerConnection.localDescription.sdp,
          type: rtcPeerConnection.localDescription.type,
        }),
      });

      if (!res.ok) throw new Error(`Server returned HTTP ${res.status}`);
      const answer = await res.json();
      await rtcPeerConnection.setRemoteDescription(new RTCSessionDescription(answer));
      console.log("[WebRTC] Connected 60 FPS screen mirror!");
    } catch (err) {
      console.warn("[WebRTC connection failed, activating stream fallback]", err);
      activateStreamFallback();
    }
  }

  function stopWebRTCScreen() {
    if (webRtcWatchdog) clearTimeout(webRtcWatchdog);
    sendWS("stop_screen_stream");
    stopHttpFrameLoop();
    updateScreenMicState(false);
    if (rtcMicStream) {
      rtcMicStream.getTracks().forEach((t) => t.stop());
      rtcMicStream = null;
    }
    if (rtcPeerConnection) {
      rtcPeerConnection.close();
      rtcPeerConnection = null;
    }
    rtcDataChannel = null;
    if (screenStreamVideo) {
      if (screenStreamVideo.srcObject) {
        try {
          screenStreamVideo.srcObject.getTracks().forEach((t) => t.stop());
        } catch (e) {}
      }
      screenStreamVideo.srcObject = null;
      screenStreamVideo.style.display = "none";
    }
    if (screenStreamImg) {
      screenStreamImg.src = "";
      screenStreamImg.style.display = "none";
    }
  }

  function toggleScreenMirror(force) {
    screenMirrorOpen = typeof force === "boolean" ? force : !screenMirrorOpen;
    if (screenMirrorOpen) {
      screenMirrorOverlay.style.display = "flex";
      btnToggleScreenMirror.classList.add("active");
      startWebRTCScreen();
    } else {
      screenMirrorOverlay.style.display = "none";
      btnToggleScreenMirror.classList.remove("active");
      stopWebRTCScreen();
    }
  }

  btnToggleScreenMirror.addEventListener("click", () => toggleScreenMirror());
  btnCloseScreenMirror.addEventListener("click", () => toggleScreenMirror(false));

  btnScreenFullscreen.addEventListener("click", () => {
    if (!document.fullscreenElement) {
      screenMirrorOverlay.requestFullscreen().then(() => {
        if (screen.orientation && screen.orientation.lock) {
          screen.orientation.lock("landscape").catch(() => {});
        }
      }).catch(() => {});
    } else {
      document.exitFullscreen().then(() => {
        if (screen.orientation && screen.orientation.unlock) {
          screen.orientation.unlock();
        }
      }).catch(() => {});
    }
  });

  btnToggleTouchClicks.addEventListener("click", () => {
    touchClicksEnabled = !touchClicksEnabled;
    touchClickLabel.textContent = touchClicksEnabled ? "Touch" : "Touch: OFF";
    btnToggleTouchClicks.classList.toggle("active", touchClicksEnabled);
  });

  const screenViewportWrap = document.getElementById("screenViewportWrap");
  let touchStartTime = 0;
  let touchStartX = 0;
  let touchStartY = 0;
  let touchMoved = false;

  function calculateVideoRenderedBounds() {
    const target = (screenStreamVideo && screenStreamVideo.style.display !== "none")
      ? screenStreamVideo
      : screenStreamImg;
    if (!target) return null;

    const wrap = screenViewportWrap || target.parentElement;
    if (!wrap) return null;
    const wrapRect = wrap.getBoundingClientRect();

    // Get true intrinsic video resolution
    let videoW = target.videoWidth || (target.naturalWidth || 1920);
    let videoH = target.videoHeight || (target.naturalHeight || 1080);
    if (!videoW || !videoH) {
      videoW = 1920;
      videoH = 1080;
    }
    const videoAR = videoW / videoH;
    const containerAR = wrapRect.width / wrapRect.height;

    let renderedW, renderedH, offsetX, offsetY;

    if (containerAR < videoAR) {
      // Letterboxed top and bottom (e.g. portrait phone)
      renderedW = wrapRect.width;
      renderedH = wrapRect.width / videoAR;
      offsetX = 0;
      offsetY = (wrapRect.height - renderedH) / 2;
    } else {
      // Pillarboxed left and right (e.g. landscape)
      renderedH = wrapRect.height;
      renderedW = wrapRect.height * videoAR;
      offsetX = (wrapRect.width - renderedW) / 2;
      offsetY = 0;
    }

    return {
      wrapRect,
      renderedW,
      renderedH,
      offsetX,
      offsetY,
    };
  }

  function sendRemoteClick(clientX, clientY, button = "left") {
    if (!touchClicksEnabled) return;

    const bounds = calculateVideoRenderedBounds();
    if (!bounds) return;

    const { wrapRect, renderedW, renderedH, offsetX, offsetY } = bounds;

    // Untransform coordinate based on currentZoom and panX, panY
    const centerX = wrapRect.left + wrapRect.width / 2;
    const centerY = wrapRect.top + wrapRect.height / 2;

    const unscaledX = (clientX - centerX - panX) / currentZoom + wrapRect.width / 2;
    const unscaledY = (clientY - centerY - panY) / currentZoom + wrapRect.height / 2;

    // Convert coordinate relative to actual rendered video frame
    const frameX = unscaledX - offsetX;
    const frameY = unscaledY - offsetY;

    // If tap is far outside the video frame in the black bars, ignore
    if (frameX < -25 || frameX > renderedW + 25 || frameY < -25 || frameY > renderedH + 25) {
      return;
    }

    const normX = Math.max(0.0, Math.min(1.0, frameX / renderedW));
    const normY = Math.max(0.0, Math.min(1.0, frameY / renderedH));

    // Show visual click ripple at exact touch contact point under user's finger
    if (screenClickRipple && screenViewportWrap) {
      screenClickRipple.style.left = `${clientX - wrapRect.left}px`;
      screenClickRipple.style.top = `${clientY - wrapRect.top}px`;
      screenClickRipple.classList.remove("animate");
      void screenClickRipple.offsetWidth;
      screenClickRipple.classList.add("animate");
    }

    console.log(`[Remote Click] Sending ${button} click at normalized (${normX.toFixed(4)}, ${normY.toFixed(4)})`);

    // 1. Send via WebRTC DataChannel (sub-millisecond instant execution)
    let sent = false;
    if (rtcDataChannel && rtcDataChannel.readyState === "open") {
      try {
        rtcDataChannel.send(JSON.stringify({ type: "click", x: normX, y: normY, button }));
        sent = true;
      } catch (e) {}
    }

    // 2. Otherwise send via WebSocket
    if (!sent) {
      sent = sendWS("screen_click", { x: normX, y: normY, button });
    }

    // 3. HTTP API fallback only if WebRTC and WebSocket are both unavailable
    if (!sent) {
      authFetch("/api/screen/click", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ x: normX, y: normY, button }),
      }).catch(() => {});
    }
  }

  if (screenViewportWrap) {
    // Touch Events: Pinch-to-Zoom, 1-finger Pan, and Instant Tap Detection
    screenViewportWrap.addEventListener("touchstart", (e) => {
      if (e.touches.length === 2) {
        isDraggingScreen = false;
        touchMoved = true;
        const dx = e.touches[0].clientX - e.touches[1].clientX;
        const dy = e.touches[0].clientY - e.touches[1].clientY;
        initialPinchDistance = Math.hypot(dx, dy);
        initialZoom = currentZoom;
      } else if (e.touches.length === 1) {
        startTouchX = e.touches[0].clientX;
        startTouchY = e.touches[0].clientY;
        touchStartX = e.touches[0].clientX;
        touchStartY = e.touches[0].clientY;
        touchStartTime = performance.now();
        touchMoved = false;
        isDraggingScreen = currentZoom > 1.05;
      }
    }, { passive: true });

    screenViewportWrap.addEventListener("touchmove", (e) => {
      if (e.touches.length === 2 && initialPinchDistance > 0) {
        touchMoved = true;
        const dx = e.touches[0].clientX - e.touches[1].clientX;
        const dy = e.touches[0].clientY - e.touches[1].clientY;
        const currentDistance = Math.hypot(dx, dy);
        const scaleFactor = currentDistance / initialPinchDistance;
        const newZoom = Math.max(1.0, Math.min(3.5, initialZoom * scaleFactor));
        currentZoom = newZoom;
        applyScreenTransform(false);
        if (screenFitLabel) {
          screenFitLabel.textContent = currentZoom > 1.05 ? `${Math.round(currentZoom * 100)}%` : "Fit";
        }
      } else if (e.touches.length === 1) {
        const moveX = e.touches[0].clientX - startTouchX;
        const moveY = e.touches[0].clientY - startTouchY;
        const totalDist = Math.hypot(e.touches[0].clientX - touchStartX, e.touches[0].clientY - touchStartY);
        if (totalDist > 8) {
          touchMoved = true;
        }
        if (isDraggingScreen) {
          panX += moveX;
          panY += moveY;
          startTouchX = e.touches[0].clientX;
          startTouchY = e.touches[0].clientY;
          applyScreenTransform(false);
        }
      }
    }, { passive: true });

    screenViewportWrap.addEventListener("touchend", (e) => {
      if (e.touches.length < 2) {
        initialPinchDistance = 0;
      }
      if (e.touches.length === 0) {
        isDraggingScreen = false;
        applyScreenTransform(true);
      }

      // Handle Tap Click on phone touch
      if (!touchMoved && e.changedTouches.length === 1) {
        const touch = e.changedTouches[0];
        const tapDuration = performance.now() - touchStartTime;
        if (tapDuration < 350) {
          const now = performance.now();
          if (now - lastTapTime < 320) {
            // Double tap: toggle zoom in/out
            if (currentZoom > 1.05) {
              setScreenZoom(1.0);
            } else {
              setScreenZoom(2.0, touch.clientX, touch.clientY);
            }
            lastTapTime = 0;
            return;
          }
          lastTapTime = now;
          sendRemoteClick(touch.clientX, touch.clientY, "left");
        }
      }
    });

    // Desktop/Mouse Click Handler
    screenViewportWrap.addEventListener("click", (e) => {
      // If triggered by mouse (detail > 0)
      if (e.pointerType === "mouse" || (!e.pointerType && e.clientX)) {
        sendRemoteClick(e.clientX, e.clientY, "left");
      }
    });
  }

  // ========================================================================
  // Phone Microphone & In-Browser Dictation
  // ========================================================================
  let mediaRecorder = null;
  let audioChunks = [];
  let speechRec = null;
  let isMobileRecording = false;
  let micAudioStream = null;
  let micMeterInterval = null;
  let sentViaSpeechRec = false;

  const agentActionPill = document.getElementById("agentActionPill");

  // Floating Toast notification when a web app or YouTube is opened
  function showWebAppOpenedToast(appName, url, msg) {
    let toast = document.getElementById("webAppOpenedToast");
    if (!toast) {
      toast = document.createElement("div");
      toast.id = "webAppOpenedToast";
      toast.className = "web-app-toast";
      document.body.appendChild(toast);
    }
    const isYouTube = (appName && appName.toLowerCase().includes("youtube")) || (url && url.includes("youtube.com"));
    const icon = isYouTube ? "▶️" : "🚀";
    const cleanApp = appName ? appName : (isYouTube ? "YouTube Video" : "Web App");
    const btnLabel = isYouTube ? "Watch on Phone ↗" : "Open on Phone ↗";
    toast.innerHTML = `
      <span class="web-app-toast-text">${icon} ${escapeHtml(cleanApp)} (Playing on Laptop)</span>
      ${url ? `<a href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer" class="web-app-toast-btn">${btnLabel}</a>` : ""}
    `;
    toast.classList.add("show");
    setTimeout(() => {
      if (toast) toast.classList.remove("show");
    }, 7000);

    // Also display prominent action button below response box on phone screen
    if (agentActionPill && url) {
      agentActionPill.innerHTML = `
        <a href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer" class="agent-action-link">
          ${icon} ${isYouTube ? "Watch" : "Open"} ${escapeHtml(cleanApp)} on this Phone ↗
        </a>
      `;
      agentActionPill.style.display = "inline-flex";
    }
  }

  // Web Speech API for zero-latency client dictation if supported
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (SpeechRecognition) {
    try {
      speechRec = new SpeechRecognition();
      speechRec.continuous = false;
      speechRec.interimResults = true;
      speechRec.lang = "en-US";

      speechRec.onresult = (event) => {
        let interim = "";
        for (let i = event.resultIndex; i < event.results.length; ++i) {
          if (event.results[i].isFinal) {
            const finalTxt = event.results[i][0].transcript.trim();
            if (finalTxt) {
              sentViaSpeechRec = true;
              userUtterance.textContent = `"${finalTxt}"`;
              userUtterance.classList.remove("is-placeholder");
              sendWS("send_text", { text: finalTxt });
              stopTalking();
            }
          } else {
            interim += event.results[i][0].transcript;
          }
        }
        if (interim) {
          userUtterance.textContent = `"${interim}..."`;
          userUtterance.classList.remove("is-placeholder");
        }
      };

      speechRec.onerror = (e) => {
        console.warn("[speechRec error]", e);
      };
    } catch (e) {
      console.warn("[speechRec init error]", e);
    }
  }

  // Security Context Check for Mobile Phone Microphones
  function checkMobileMicSecurity() {
    if (location.protocol === "http:" && location.hostname !== "localhost" && location.hostname !== "127.0.0.1") {
      const httpsUrl = `https://${location.host}`;
      userUtterance.innerHTML = `<span style="color: var(--accent-amber);">🔒 Phone mic requires HTTPS. <a href="${httpsUrl}" style="color: var(--accent-cyan); text-decoration: underline; font-weight: bold;">Tap here to switch to HTTPS</a> (then click Advanced → Proceed).</span>`;
      userUtterance.classList.remove("is-placeholder");
      return false;
    }
    return true;
  }

  // Check on mobile startup
  if (isMobileDevice) {
    checkMobileMicSecurity();
    const phoneKbd = document.querySelector(".btn-push-to-talk .kbd-badge");
    if (phoneKbd) phoneKbd.style.display = "none";
    if (btnPushToTalk) {
      btnPushToTalk.setAttribute("title", "Tap to Talk");
      btnPushToTalk.setAttribute("aria-label", "Tap to Talk");
    }
  }

  async function startPhoneRecording() {
    if (isMobileRecording) return;

    if (!checkMobileMicSecurity()) {
      return;
    }

    sentViaSpeechRec = false;
    isMobileRecording = true;
    playSoundCue("listen");
    userUtterance.textContent = '"Listening... Speak now!"';
    userUtterance.classList.remove("is-placeholder");

    if (btnScreenDictate) {
      btnScreenDictate.classList.add("recording");
      screenDictateLabel.textContent = "Listening... Release to Send";
    }

    if (speechRec) {
      try {
        speechRec.start();
      } catch (e) {}
    }

    try {
      micAudioStream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });

      // Hook up real-time audio meter & Voice Activity Detection on mobile
      try {
        const actx = getAudioContext();
        if (actx.state === "suspended") actx.resume();
        const source = actx.createMediaStreamSource(micAudioStream);
        const analyser = actx.createAnalyser();
        analyser.fftSize = 256;
        source.connect(analyser);

        const dataArr = new Uint8Array(analyser.frequencyBinCount);
        let hasSpoken = false;
        let silentFrames = 0;
        let totalFrames = 0;

        if (micMeterInterval) clearInterval(micMeterInterval);
        micMeterInterval = setInterval(() => {
          if (!isMobileRecording) return;
          totalFrames++;
          analyser.getByteFrequencyData(dataArr);
          let sum = 0;
          for (let i = 0; i < dataArr.length; i++) sum += dataArr[i];
          const avg = sum / dataArr.length;
          const level = Math.min(1.0, avg / 80.0);
          if (orb) orb.setAudioLevel(level);
          updateVisualizer(level);

          // Intelligent mobile silence detection:
          // Once the user speaks (level > 0.12), if they stop speaking for ~1.4s, automatically send
          if (level > 0.12) {
            hasSpoken = true;
            silentFrames = 0;
          } else if (hasSpoken) {
            silentFrames++;
            if (silentFrames >= 35) { // 35 * 40ms = 1.4s of silence
              stopTalking();
            }
          }
          // Max safeguard: 9 seconds
          if (totalFrames >= 225) {
            stopTalking();
          }
        }, 40);
      } catch (e) {
        console.warn("[audio meter init error]", e);
      }

      audioChunks = [];
      let mimeType = "audio/webm;codecs=opus";
      if (!MediaRecorder.isTypeSupported(mimeType)) {
        if (MediaRecorder.isTypeSupported("audio/webm")) {
          mimeType = "audio/webm";
        } else if (MediaRecorder.isTypeSupported("audio/mp4")) {
          mimeType = "audio/mp4";
        } else if (MediaRecorder.isTypeSupported("audio/ogg")) {
          mimeType = "audio/ogg";
        } else {
          mimeType = "";
        }
      }

      mediaRecorder = mimeType ? new MediaRecorder(micAudioStream, { mimeType }) : new MediaRecorder(micAudioStream);
      mediaRecorder.ondataavailable = (e) => {
        if (e.data.size > 0) audioChunks.push(e.data);
      };
      mediaRecorder.onstop = () => {
        if (micMeterInterval) {
          clearInterval(micMeterInterval);
          micMeterInterval = null;
        }
        if (micAudioStream) {
          micAudioStream.getTracks().forEach((t) => t.stop());
          micAudioStream = null;
        }
        // Only send raw audio if Web Speech API didn't already transcribe and dispatch it
        if (audioChunks.length > 0 && !sentViaSpeechRec) {
          const blob = new Blob(audioChunks, { type: mediaRecorder.mimeType || "audio/webm" });
          const reader = new FileReader();
          reader.onloadend = () => {
            const base64Data = reader.result;
            sendWS("mobile_audio", { audio: base64Data });
          };
          reader.readAsDataURL(blob);
        }
      };
      // Request chunks every 250ms for reliable recording across mobile browsers
      mediaRecorder.start(250);
    } catch (err) {
      console.error("[phone mic getUserMedia error]", err);
      isMobileRecording = false;
      if (btnScreenDictate) {
        btnScreenDictate.classList.remove("recording");
        screenDictateLabel.textContent = "Hold to Dictate to Laptop";
      }
      userUtterance.innerHTML = `<span style="color: var(--accent-rose);">⚠️ Mic Error: ${err.message || "Permission Denied"}. Ensure you are on HTTPS and allow microphone permissions.</span>`;
      userUtterance.classList.remove("is-placeholder");
    }
  }

  function stopPhoneRecording() {
    if (!isMobileRecording) return;
    isMobileRecording = false;
    playSoundCue("done");

    if (micMeterInterval) {
      clearInterval(micMeterInterval);
      micMeterInterval = null;
    }

    if (btnScreenDictate) {
      btnScreenDictate.classList.remove("recording");
      screenDictateLabel.textContent = "Processing speech...";
      setTimeout(() => {
        if (!isMobileRecording && btnScreenDictate) {
          screenDictateLabel.textContent = "Hold or Speak to Dictate";
        }
      }, 2500);
    }

    if (speechRec) {
      try {
        speechRec.stop();
      } catch (e) {}
    }

    if (mediaRecorder && mediaRecorder.state !== "inactive") {
      try {
        mediaRecorder.requestData();
      } catch (e) {}
      mediaRecorder.stop();
    }
  }

  if (btnScreenDictate) {
    btnScreenDictate.addEventListener("mousedown", (e) => {
      e.preventDefault();
      startPhoneRecording();
    });
    btnScreenDictate.addEventListener("mouseup", (e) => {
      e.preventDefault();
      stopPhoneRecording();
    });
    btnScreenDictate.addEventListener("mouseleave", () => {
      if (isMobileRecording) stopPhoneRecording();
    });
    btnScreenDictate.addEventListener("touchstart", (e) => {
      e.preventDefault();
      startPhoneRecording();
    }, { passive: false });
    btnScreenDictate.addEventListener("touchend", (e) => {
      e.preventDefault();
      stopPhoneRecording();
    }, { passive: false });
    btnScreenDictate.addEventListener("touchcancel", () => {
      if (isMobileRecording) stopPhoneRecording();
    });
  }

  // ========================================================================
  // Mobile Connect & QR Code Modal (Local Wi-Fi & Remote Anywhere)
  // ========================================================================
  function updateMobileConnectInfo(url) {
    if (!url) return;
    if (mobileUrlDisplay) mobileUrlDisplay.textContent = url;
    if (mobileQrImg) {
      mobileQrImg.src = `https://api.qrserver.com/v1/create-qr-code/?size=220x220&data=${encodeURIComponent(url)}`;
    }
  }

  function updateTunnelUI(tunnel) {
    if (!tunnel || !remoteTunnelStatusPill) return;

    const statusLabel = document.getElementById("remoteTunnelStatusLabel") || remoteTunnelStatusPill;

    if (tunnel.active && tunnel.public_url) {
      remoteTunnelStatusPill.className = "tunnel-status-pill active";
      statusLabel.textContent = "Tunnel: Active (Online)";
      if (remoteTunnelSubtext) remoteTunnelSubtext.textContent = "Cloudflare secure tunnel running";
      if (btnToggleTunnel) {
        btnToggleTunnel.textContent = "Stop Remote Tunnel";
        btnToggleTunnel.className = "btn-secondary";
        btnToggleTunnel.disabled = false;
      }
      if (remoteActiveContent) remoteActiveContent.style.display = "flex";
      if (remoteInactiveContent) remoteInactiveContent.style.display = "none";

      const tokenPart = currentAuthToken ? `?token=${encodeURIComponent(currentAuthToken)}` : "";
      const remoteAuthUrl = tunnel.authenticated_url || `${tunnel.public_url}${tokenPart}`;
      if (remoteUrlDisplay) remoteUrlDisplay.textContent = remoteAuthUrl;
      if (remoteQrImg) {
        remoteQrImg.src = `https://api.qrserver.com/v1/create-qr-code/?size=220x220&data=${encodeURIComponent(remoteAuthUrl)}`;
      }
    } else if (tunnel.status === "starting" || tunnel.starting) {
      remoteTunnelStatusPill.className = "tunnel-status-pill starting";
      statusLabel.textContent = "Tunnel: Connecting...";
      if (remoteTunnelSubtext) remoteTunnelSubtext.textContent = "Establishing Cloudflare edge connection...";
      if (btnToggleTunnel) {
        btnToggleTunnel.textContent = "Starting...";
        btnToggleTunnel.className = "btn-secondary";
        btnToggleTunnel.disabled = true;
      }
      if (remoteActiveContent) remoteActiveContent.style.display = "none";
      if (remoteInactiveContent) remoteInactiveContent.style.display = "flex";
    } else {
      remoteTunnelStatusPill.className = "tunnel-status-pill idle";
      statusLabel.textContent = "Tunnel: Inactive";
      if (remoteTunnelSubtext) {
        remoteTunnelSubtext.textContent = tunnel.error ? `Error: ${tunnel.error}` : "Ready to connect over cellular data";
      }
      if (btnToggleTunnel) {
        btnToggleTunnel.textContent = "Start Remote Tunnel";
        btnToggleTunnel.className = "btn-primary";
        btnToggleTunnel.disabled = false;
      }
      if (remoteActiveContent) remoteActiveContent.style.display = "none";
      if (remoteInactiveContent) remoteInactiveContent.style.display = "flex";
    }
  }

  // Switch between Local Wi-Fi and Remote Anywhere tabs
  function switchMobileTab(mode) {
    if (mode === "remote") {
      if (btnTabLocalWifi) {
        btnTabLocalWifi.classList.remove("active");
        btnTabLocalWifi.setAttribute("aria-selected", "false");
      }
      if (btnTabRemoteTunnel) {
        btnTabRemoteTunnel.classList.add("active");
        btnTabRemoteTunnel.setAttribute("aria-selected", "true");
      }
      if (paneLocalWifi) {
        paneLocalWifi.classList.remove("active");
        paneLocalWifi.style.display = "none";
      }
      if (paneRemoteTunnel) {
        paneRemoteTunnel.classList.add("active");
        paneRemoteTunnel.style.display = "flex";
      }
      fetchTunnelStatus();
    } else {
      if (btnTabRemoteTunnel) {
        btnTabRemoteTunnel.classList.remove("active");
        btnTabRemoteTunnel.setAttribute("aria-selected", "false");
      }
      if (btnTabLocalWifi) {
        btnTabLocalWifi.classList.add("active");
        btnTabLocalWifi.setAttribute("aria-selected", "true");
      }
      if (paneRemoteTunnel) {
        paneRemoteTunnel.classList.remove("active");
        paneRemoteTunnel.style.display = "none";
      }
      if (paneLocalWifi) {
        paneLocalWifi.classList.add("active");
        paneLocalWifi.style.display = "flex";
      }
    }
  }

  if (btnTabLocalWifi) {
    btnTabLocalWifi.addEventListener("click", () => switchMobileTab("wifi"));
  }
  if (btnTabRemoteTunnel) {
    btnTabRemoteTunnel.addEventListener("click", () => switchMobileTab("remote"));
  }

  let tunnelPollInterval = null;

  async function fetchTunnelStatus() {
    try {
      const res = await authFetch("/api/tunnel/status").then((r) => r.json());
      if (res) updateTunnelUI(res);
      return res;
    } catch (e) {
      console.warn("[tunnel status error]", e);
      return null;
    }
  }

  if (btnToggleTunnel) {
    btnToggleTunnel.addEventListener("click", async () => {
      const isCurrentlyActive = remoteTunnelStatusPill && remoteTunnelStatusPill.classList.contains("active");
      const shouldEnable = !isCurrentlyActive;

      updateTunnelUI({ status: shouldEnable ? "starting" : "stopped" });

      try {
        const res = await authFetch("/api/tunnel/toggle", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ enable: shouldEnable }),
        }).then((r) => r.json());

        if (res && res.tunnel) {
          updateTunnelUI(res.tunnel);
        }

        if (shouldEnable) {
          if (tunnelPollInterval) clearInterval(tunnelPollInterval);
          let pollAttempts = 0;
          tunnelPollInterval = setInterval(async () => {
            pollAttempts++;
            const statusRes = await fetchTunnelStatus();
            const isTerminal = statusRes && (statusRes.active || statusRes.status === "error" || statusRes.status === "stopped");
            if (isTerminal || pollAttempts >= 30) {
              clearInterval(tunnelPollInterval);
              tunnelPollInterval = null;
            }
          }, 1500);
        }
      } catch (err) {
        console.error("[tunnel toggle error]", err);
        fetchTunnelStatus();
      }
    });
  }

  if (btnOpenMobileConnect) {
    btnOpenMobileConnect.addEventListener("click", async () => {
      mobileConnectModal.classList.add("active");
      try {
        const res = await authFetch("/api/network-info").then((r) => r.json());
        if (res) {
          if (res.local_url || res.url) updateMobileConnectInfo(res.local_url || res.url);
          if (res.auth_token) currentAuthToken = res.auth_token;
          if (res.tunnel) updateTunnelUI(res.tunnel);
        }
      } catch (e) {
        console.warn("[network-info error]", e);
      }
    });
  }

  if (btnCloseMobileConnect) {
    btnCloseMobileConnect.addEventListener("click", () => {
      mobileConnectModal.classList.remove("active");
    });
  }

  if (mobileConnectModal) {
    mobileConnectModal.addEventListener("click", (e) => {
      if (e.target === mobileConnectModal) {
        mobileConnectModal.classList.remove("active");
      }
    });
  }

  if (btnCopyMobileUrl) {
    btnCopyMobileUrl.addEventListener("click", () => {
      const url = mobileUrlDisplay ? mobileUrlDisplay.textContent : "";
      if (url) {
        navigator.clipboard.writeText(url);
        const span = btnCopyMobileUrl.querySelector("span") || btnCopyMobileUrl;
        const origText = span.textContent;
        span.textContent = "Copied!";
        setTimeout(() => (span.textContent = origText), 2000);
      }
    });
  }

  if (btnCopyRemoteUrl) {
    btnCopyRemoteUrl.addEventListener("click", () => {
      const url = remoteUrlDisplay ? remoteUrlDisplay.textContent : "";
      if (url) {
        navigator.clipboard.writeText(url);
        const span = btnCopyRemoteUrl.querySelector("span") || btnCopyRemoteUrl;
        const origText = span.textContent;
        span.textContent = "Copied!";
        setTimeout(() => (span.textContent = origText), 2000);
      }
    });
  }

  // ========================================================================
  // Premium Tooltip & Micro-Popover Engine
  // ========================================================================
  (function initTooltipEngine() {
    const tooltip = document.getElementById("ecoTooltip");
    if (!tooltip) return;

    const arrow = document.getElementById("ecoTooltipArrow");
    const label = document.getElementById("ecoTooltipText");
    const sub = document.getElementById("ecoTooltipSub");
    const keys = document.getElementById("ecoTooltipKeys");
    const indicator = document.getElementById("ecoTooltipIndicator");

    let currentTarget = null;
    let showTimer = null;
    let lastHideTimestamp = 0;
    const WARM_THRESHOLD_MS = 380; // Instant switch if hovered within 380ms of previous button

    // Parse tooltip text to extract shortcuts, status indicators, and subtext
    function parseTooltipText(raw) {
      if (!raw) return null;
      let text = raw.trim();
      let shortcut = "";
      let subtext = "";
      let statusType = "";

      // Check for status like "Continuous Listening: Paused" or "Status: Active"
      const statusMatch = text.match(/^([^:]+):\s*(Active|Paused|Enabled|Disabled|On|Off|Online|Offline)$/i);
      if (statusMatch) {
        text = statusMatch[1].trim();
        subtext = statusMatch[2].trim();
        const lower = subtext.toLowerCase();
        if (["active", "enabled", "on", "online"].includes(lower)) {
          statusType = "active";
        } else if (["paused", "disabled", "off", "offline"].includes(lower)) {
          statusType = "paused";
        }
      }

      // Check for trailing parentheses like "(Ctrl+J)" or "(Ctrl+T or Esc)" or "(Escape)" or "(Alt+M)"
      const parenMatch = text.match(/\(([^)]+)\)$/);
      if (parenMatch) {
        const inside = parenMatch[1].trim();
        if (/\b(Ctrl|Alt|Shift|Esc|Escape|Enter|Space|Tilde|Tab|Cmd|Win)\b/i.test(inside)) {
          shortcut = inside;
          text = text.substring(0, parenMatch.index).trim();
        } else if (!subtext) {
          subtext = inside;
          text = text.substring(0, parenMatch.index).trim();
        }
      }

      // Check for copied or danger keywords
      if (/copied/i.test(text)) {
        statusType = "active";
      } else if (/interrupt|stop|danger|abort/i.test(text)) {
        statusType = "danger";
      }

      return { text, shortcut, subtext, statusType };
    }

    // Render parsed data into tooltip DOM
    function renderTooltipContent(parsed) {
      if (!parsed) return;
      label.textContent = parsed.text;

      // Status indicator dot
      indicator.className = "eco-tooltip-indicator";
      if (parsed.statusType) {
        indicator.classList.add(parsed.statusType);
      }

      // Subtext
      if (parsed.subtext) {
        sub.textContent = parsed.subtext;
        sub.classList.add("visible");
      } else {
        sub.textContent = "";
        sub.classList.remove("visible");
      }

      // Keyboard shortcuts
      keys.innerHTML = "";
      if (parsed.shortcut) {
        keys.classList.add("visible");
        const orParts = parsed.shortcut.split(/\s+or\s+/i);
        orParts.forEach((part, partIdx) => {
          if (partIdx > 0) {
            const sep = document.createElement("span");
            sep.className = "eco-tooltip-kbd-sep";
            sep.textContent = "or";
            keys.appendChild(sep);
          }
          const combo = part.split("+").map((s) => s.trim());
          combo.forEach((keyName, keyIdx) => {
            if (keyIdx > 0) {
              const plus = document.createElement("span");
              plus.className = "eco-tooltip-kbd-sep";
              plus.textContent = "+";
              keys.appendChild(plus);
            }
            const kbd = document.createElement("kbd");
            kbd.className = "eco-tooltip-kbd";
            kbd.textContent = keyName === "Escape" ? "Esc" : keyName;
            keys.appendChild(kbd);
          });
        });
      } else {
        keys.classList.remove("visible");
      }
    }

    // Position tooltip relative to target element with boundary collision handling
    function positionTooltip(el) {
      const targetRect = el.getBoundingClientRect();
      const tooltipRect = tooltip.getBoundingClientRect();
      const margin = 8;
      const arrowOffset = 6;

      // Determine vertical placement: top vs bottom
      let placement = "bottom";
      if (targetRect.top > window.innerHeight * 0.65 || (window.innerHeight - targetRect.bottom < tooltipRect.height + margin + 14)) {
        placement = "top";
      }

      tooltip.setAttribute("data-placement", placement);

      let top = 0;
      let left = targetRect.left + (targetRect.width / 2) - (tooltipRect.width / 2);

      // Clamp horizontal within screen bounds
      left = Math.max(margin, Math.min(window.innerWidth - tooltipRect.width - margin, left));

      if (placement === "bottom") {
        top = targetRect.bottom + arrowOffset;
      } else {
        top = targetRect.top - tooltipRect.height - arrowOffset;
      }

      tooltip.style.transform = `translate3d(${Math.round(left)}px, ${Math.round(top)}px, 0)`;

      // Align arrow with target element center
      const targetCenterX = targetRect.left + (targetRect.width / 2);
      const arrowLeft = Math.max(10, Math.min(tooltipRect.width - 14, targetCenterX - left - 4));
      arrow.style.left = `${Math.round(arrowLeft)}px`;
    }

    function showTooltipFor(el) {
      if (!el || el === currentTarget) return;

      // Check for title, data-eco-tooltip, or aria-label
      let raw = el.getAttribute("title") || el.dataset.ecoTooltip;
      if (!raw) {
        const aria = el.getAttribute("aria-label");
        if (aria && (el.tagName === "BUTTON" || el.classList.contains("icon-btn") || el.id === "orbWrapper")) {
          raw = aria;
        }
      }
      if (!raw) return;

      // Suppress browser default tooltip popup
      if (el.hasAttribute("title")) {
        el.dataset.ecoTooltip = raw;
        el.removeAttribute("title");
      }

      currentTarget = el;
      const parsed = parseTooltipText(raw);
      if (!parsed || !parsed.text) return;

      clearTimeout(showTimer);

      const isWarm = (Date.now() - lastHideTimestamp) < WARM_THRESHOLD_MS;
      const delay = isWarm ? 0 : 120;

      showTimer = setTimeout(() => {
        if (!currentTarget) return;
        renderTooltipContent(parsed);
        tooltip.classList.add("active");
        positionTooltip(currentTarget);
      }, delay);
    }

    function hideTooltip() {
      clearTimeout(showTimer);
      if (currentTarget) {
        currentTarget = null;
        lastHideTimestamp = Date.now();
        tooltip.classList.remove("active");
      }
    }

    // Global event listeners for zero-configuration discovery
    document.addEventListener("pointerover", (evt) => {
      if (evt.pointerType === "touch") return;

      const trigger = evt.target.closest(
        "button, [title], [data-eco-tooltip], .icon-btn, .mini-icon-btn, .screen-tool-btn, #orbWrapper, .btn-push-to-talk, .kbd-badge"
      );

      if (trigger) {
        showTooltipFor(trigger);
      } else {
        hideTooltip();
      }
    }, { passive: true });

    document.addEventListener("pointerout", (evt) => {
      if (currentTarget && !currentTarget.contains(evt.relatedTarget)) {
        hideTooltip();
      }
    }, { passive: true });

    // Dismiss immediately on interaction or modal close
    window.addEventListener("scroll", hideTooltip, { passive: true });
    window.addEventListener("click", hideTooltip, { passive: true });
    window.addEventListener("pointerdown", hideTooltip, { passive: true });
    window.addEventListener("blur", hideTooltip);
    document.addEventListener("keydown", (evt) => {
      if (evt.key === "Escape") hideTooltip();
    });

    // Observer to update tooltip dynamically if attributes change
    const observer = new MutationObserver((mutations) => {
      if (!currentTarget) return;
      for (const m of mutations) {
        if (m.target === currentTarget && (m.attributeName === "title" || m.attributeName === "data-eco-tooltip")) {
          const raw = currentTarget.getAttribute("title") || currentTarget.dataset.ecoTooltip;
          if (raw) {
            if (currentTarget.hasAttribute("title")) {
              currentTarget.dataset.ecoTooltip = raw;
              currentTarget.removeAttribute("title");
            }
            renderTooltipContent(parseTooltipText(raw));
            positionTooltip(currentTarget);
          }
        }
      }
    });

    observer.observe(document.body, {
      attributes: true,
      subtree: true,
      attributeFilter: ["title", "data-eco-tooltip"],
    });
  })();

  // Start WebSocket
  connectWebSocket();
})();
