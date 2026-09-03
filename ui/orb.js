/**
 * VoiceOrb — High-Performance 60 FPS Canvas Voice Visualization
 * 
 * Supports 11 explicit system states:
 *   idle, listening, hearing, processing, thinking, tool,
 *   confirmation, executing, speaking, success, error
 * 
 * Accurately responds to real-time audio amplitude from the mic & TTS.
 */

class VoiceOrb {
  constructor(canvasId) {
    this.canvas = document.getElementById(canvasId);
    if (!this.canvas) return;
    this.ctx = this.canvas.getContext("2d");

    this.state = "idle";
    this.audioLevel = 0.0;
    this.targetAudioLevel = 0.0;
    this.time = 0;
    this.lastFrameTime = performance.now();

    // Particle constellation
    this.particles = [];
    this.numParticles = 48;
    this._initParticles();

    // Colors per state
    this.stateColors = {
      idle: { core: "#00F0FF", glow: "rgba(0, 240, 255, 0.25)", ring: "rgba(0, 240, 255, 0.4)" },
      listening: { core: "#00F0FF", glow: "rgba(0, 240, 255, 0.45)", ring: "rgba(0, 240, 255, 0.7)" },
      hearing: { core: "#38BDF8", glow: "rgba(56, 189, 248, 0.55)", ring: "rgba(56, 189, 248, 0.85)" },
      processing: { core: "#6366F1", glow: "rgba(99, 102, 241, 0.4)", ring: "rgba(99, 102, 241, 0.6)" },
      thinking: { core: "#8B5CF6", glow: "rgba(139, 92, 246, 0.5)", ring: "rgba(168, 85, 247, 0.75)" },
      tool: { core: "#F59E0B", glow: "rgba(245, 158, 11, 0.45)", ring: "rgba(245, 158, 11, 0.7)" },
      confirmation: { core: "#FB923C", glow: "rgba(251, 146, 60, 0.5)", ring: "rgba(251, 146, 60, 0.8)" },
      executing: { core: "#3B82F6", glow: "rgba(59, 130, 246, 0.5)", ring: "rgba(245, 158, 11, 0.8)" },
      speaking: { core: "#06B6D4", glow: "rgba(6, 182, 212, 0.5)", ring: "rgba(56, 189, 248, 0.8)" },
      success: { core: "#10B981", glow: "rgba(16, 185, 129, 0.5)", ring: "rgba(16, 185, 129, 0.8)" },
      error: { core: "#EF4444", glow: "rgba(239, 68, 68, 0.5)", ring: "rgba(239, 68, 68, 0.8)" },
    };

    this.resize();
    window.addEventListener("resize", () => this.resize());
    this.animate = this.animate.bind(this);
    requestAnimationFrame(this.animate);
  }

  _initParticles() {
    this.particles = [];
    for (let i = 0; i < this.numParticles; i++) {
      this.particles.push({
        angle: Math.random() * Math.PI * 2,
        radiusOffset: (Math.random() - 0.5) * 40,
        speed: 0.005 + Math.random() * 0.015,
        size: 1.2 + Math.random() * 2.2,
        alpha: 0.2 + Math.random() * 0.6,
      });
    }
  }

  resize() {
    if (!this.canvas) return;
    const rect = this.canvas.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    this.width = rect.width;
    this.height = rect.height;
    this.canvas.width = this.width * dpr;
    this.canvas.height = this.height * dpr;
    this.ctx.scale(dpr, dpr);
    this.centerX = this.width / 2;
    this.centerY = this.height / 2;
    this.baseRadius = Math.min(this.width, this.height) * 0.26;
  }

  setState(state) {
    if (this.stateColors[state]) {
      this.state = state;
    }
  }

  setAudioLevel(level) {
    this.targetAudioLevel = Math.max(0.0, Math.min(1.0, level));
  }

  animate(currentTime) {
    const dt = (currentTime - this.lastFrameTime) / 1000;
    this.lastFrameTime = currentTime;
    this.time += dt;

    // Smooth audio level interpolation
    this.audioLevel += (this.targetAudioLevel - this.audioLevel) * 0.25;

    this.render();
    requestAnimationFrame(this.animate);
  }

  render() {
    const ctx = this.ctx;
    if (!ctx) return;

    ctx.clearRect(0, 0, this.width, this.height);
    const colors = this.stateColors[this.state] || this.stateColors.idle;

    // Dynamic scale driven by state and mic amplitude
    let pulse = Math.sin(this.time * 2.2) * 0.05;
    let amplitudeScale = this.audioLevel * 0.35;
    let currentRadius = this.baseRadius * (1 + pulse + amplitudeScale);

    if (this.state === "listening") {
      currentRadius *= 1.05;
    } else if (this.state === "hearing") {
      currentRadius *= 1.12;
    } else if (this.state === "thinking") {
      currentRadius *= 0.98;
    }

    // 1. Ambient Outer Luminous Glow
    const glowGrad = ctx.createRadialGradient(
      this.centerX, this.centerY, currentRadius * 0.2,
      this.centerX, this.centerY, currentRadius * 1.8
    );
    glowGrad.addColorStop(0, colors.glow);
    glowGrad.addColorStop(0.5, colors.glow.replace(/[\d.]+\)$/, "0.08)"));
    glowGrad.addColorStop(1, "transparent");

    ctx.fillStyle = glowGrad;
    ctx.beginPath();
    ctx.arc(this.centerX, this.centerY, currentRadius * 1.8, 0, Math.PI * 2);
    ctx.fill();

    // 2. Orbital Particles
    this._renderParticles(ctx, currentRadius, colors);

    // 3. State-Specific Geometries & Harmonic Waves
    if (this.state === "thinking") {
      this._renderThinkingRings(ctx, currentRadius, colors);
    } else if (this.state === "tool" || this.state === "executing") {
      this._renderSegmentedToolRings(ctx, currentRadius, colors);
    } else if (this.state === "speaking") {
      this._renderSpeakingWaves(ctx, currentRadius, colors);
    } else {
      this._renderHarmonicRings(ctx, currentRadius, colors);
    }

    // 4. Center Core Sphere
    const coreGrad = ctx.createRadialGradient(
      this.centerX - currentRadius * 0.25,
      this.centerY - currentRadius * 0.25,
      currentRadius * 0.1,
      this.centerX,
      this.centerY,
      currentRadius
    );
    coreGrad.addColorStop(0, "#FFFFFF");
    coreGrad.addColorStop(0.4, colors.core);
    coreGrad.addColorStop(0.85, colors.core.replace(/rgb\(/, "rgba(").replace(/\)$/, ", 0.4)"));
    coreGrad.addColorStop(1, "rgba(6, 8, 13, 0.9)");

    ctx.save();
    ctx.shadowColor = colors.core;
    ctx.shadowBlur = 18 + this.audioLevel * 24;
    ctx.fillStyle = coreGrad;
    ctx.beginPath();
    ctx.arc(this.centerX, this.centerY, currentRadius * 0.72, 0, Math.PI * 2);
    ctx.fill();
    ctx.restore();

    // 5. Inner Iris / Aperture Ring
    ctx.strokeStyle = "rgba(255, 255, 255, 0.45)";
    ctx.lineWidth = 1.2;
    ctx.beginPath();
    ctx.arc(this.centerX, this.centerY, currentRadius * 0.4, 0, Math.PI * 2);
    ctx.stroke();
  }

  _renderParticles(ctx, radius, colors) {
    ctx.fillStyle = colors.core;
    const speedMult = this.state === "thinking" ? 2.5 : this.state === "hearing" ? 1.8 : 1.0;

    for (let p of this.particles) {
      p.angle += p.speed * speedMult;
      const r = radius * 1.25 + p.radiusOffset + Math.sin(this.time * 3 + p.angle) * 8;
      const x = this.centerX + Math.cos(p.angle) * r;
      const y = this.centerY + Math.sin(p.angle) * r;

      ctx.globalAlpha = p.alpha * (0.6 + this.audioLevel * 0.4);
      ctx.beginPath();
      ctx.arc(x, y, p.size, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.globalAlpha = 1.0;
  }

  _renderHarmonicRings(ctx, radius, colors) {
    const numRings = 2;
    for (let i = 0; i < numRings; i++) {
      const ringRadius = radius * (1.15 + i * 0.22);
      const angleOffset = (i % 2 === 0 ? 1 : -1) * this.time * 0.8;

      ctx.strokeStyle = colors.ring;
      ctx.lineWidth = 1.4;
      ctx.beginPath();

      const points = 64;
      for (let j = 0; j <= points; j++) {
        const theta = (j / points) * Math.PI * 2;
        const wave = Math.sin(theta * 6 + angleOffset) * (4 + this.audioLevel * 14);
        const r = ringRadius + wave;
        const x = this.centerX + Math.cos(theta) * r;
        const y = this.centerY + Math.sin(theta) * r;
        if (j === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }
      ctx.stroke();
    }
  }

  _renderThinkingRings(ctx, radius, colors) {
    // Dual Counter-rotating Quantum Rings
    ctx.lineWidth = 2.0;

    // Clockwise Ring
    ctx.save();
    ctx.strokeStyle = colors.ring;
    ctx.beginPath();
    ctx.arc(this.centerX, this.centerY, radius * 1.25, this.time * 2.5, this.time * 2.5 + Math.PI * 1.4);
    ctx.stroke();
    ctx.restore();

    // Counter-Clockwise Outer Ring
    ctx.save();
    ctx.strokeStyle = "rgba(192, 132, 252, 0.85)";
    ctx.beginPath();
    ctx.arc(this.centerX, this.centerY, radius * 1.45, -this.time * 3.2, -this.time * 3.2 + Math.PI * 1.2);
    ctx.stroke();
    ctx.restore();
  }

  _renderSegmentedToolRings(ctx, radius, colors) {
    // Technical segmented locking ring
    ctx.lineWidth = 2.5;
    ctx.strokeStyle = colors.ring;
    const segments = 8;
    const step = (Math.PI * 2) / segments;

    for (let i = 0; i < segments; i++) {
      const startAngle = i * step + this.time * 1.5;
      const endAngle = startAngle + step * 0.65;
      ctx.beginPath();
      ctx.arc(this.centerX, this.centerY, radius * 1.3, startAngle, endAngle);
      ctx.stroke();
    }
  }

  _renderSpeakingWaves(ctx, radius, colors) {
    // Fluid Acoustic Bloom Waves
    const waveCount = 3;
    for (let i = 0; i < waveCount; i++) {
      const progress = ((this.time * 1.2 + i * 0.33) % 1.0);
      const r = radius * (1.0 + progress * 0.75);
      const alpha = (1.0 - progress) * 0.7;

      ctx.strokeStyle = colors.ring.replace(/[\d.]+\)$/, `${alpha})`);
      ctx.lineWidth = 2.0 - progress * 1.0;
      ctx.beginPath();
      ctx.arc(this.centerX, this.centerY, r, 0, Math.PI * 2);
      ctx.stroke();
    }
  }
}

window.VoiceOrb = VoiceOrb;
