/**
 * ECOWHISPER Desktop — Electron Preload Bridge
 * Secure ContextBridge exposing native window controls, system diagnostics,
 * global shortcuts, and notifications to the UI Command Center.
 */

const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('electronAPI', {
  isElectron: true,

  // Window Controls
  minimize: () => ipcRenderer.invoke('window:minimize'),
  maximize: () => ipcRenderer.invoke('window:maximize'),
  close: () => ipcRenderer.invoke('window:close'),
  isMaximized: () => ipcRenderer.invoke('window:isMaximized'),
  togglePin: () => ipcRenderer.invoke('window:togglePin'),
  isPinned: () => ipcRenderer.invoke('window:isPinned'),

  onMaximizeChange: (callback) => {
    const listener = (_event, isMax) => callback(isMax);
    ipcRenderer.on('window:maximizeChanged', listener);
    return () => ipcRenderer.removeListener('window:maximizeChanged', listener);
  },

  // Global Shortcuts
  onGlobalPTT: (callback) => {
    const listener = () => callback();
    ipcRenderer.on('global:ptt', listener);
    return () => ipcRenderer.removeListener('global:ptt', listener);
  },

  onGlobalMute: (callback) => {
    const listener = () => callback();
    ipcRenderer.on('global:mute', listener);
    return () => ipcRenderer.removeListener('global:mute', listener);
  },

  // Desktop Native Notifications
  showNotification: (options) => ipcRenderer.invoke('notification:send', options),

  // Hardware and System Diagnostics
  getSystemSpecs: () => ipcRenderer.invoke('system:specs'),

  // System Tray Updates
  updateTrayStatus: (status) => ipcRenderer.invoke('tray:update', status),

  // External URLs
  openExternal: (url) => ipcRenderer.invoke('shell:openExternal', url),
});
