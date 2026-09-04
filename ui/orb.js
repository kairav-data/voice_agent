/**
 * VoiceOrb — World-Class 60 FPS Canvas Voice Visualization
 * 
 * Cinematic, volumetric, organic fluid plasma orb with real-time audio reactivity.
 * Features 11 explicit system states:
 *   idle, listening, hearing, processing, thinking, tool,
 *   confirmation, executing, speaking, success, error
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
    this.numParticles = 54;
    this._initParticles();

    // Dual Luminous Color Palettes (Light Jewel-Tone Default & Dark Obsidian Neon)
    this.lightStateColors = {
      idle: {
        coreCenter: "#FFFFFF",
        coreMid: "#0284C7",
        coreOuter: "rgba(2, 132, 199, 0.45)",
        coreDeep: "rgba(12, 74, 110, 0.95)",
        glow: "rgba(2, 132, 199, 0.18)",
        ring: "rgba(2, 132, 199, 0.55)",
        particle: "rgba(2, 132, 199, 0.8)",
      },
      listening: {
        coreCenter: "#FFFFFF",
        coreMid: "#0284C7",
        coreOuter: "rgba(14, 165, 233, 0.6)",
        coreDeep: "rgba(7, 89, 133, 0.95)",
        glow: "rgba(2, 132, 199, 0.32)",
        ring: "rgba(2, 132, 199, 0.85)",
        particle: "rgba(2, 132, 199, 0.9)",
      },
      hearing: {
        coreCenter: "#FFFFFF",
        coreMid: "#2563EB",
        coreOuter: "rgba(37, 99, 235, 0.65)",
        coreDeep: "rgba(30, 58, 138, 0.95)",
        glow: "rgba(37, 99, 235, 0.35)",
        ring: "rgba(37, 99, 235, 0.85)",
        particle: "rgba(59, 130, 246, 0.9)",
      },
      processing: {
        coreCenter: "#FFFFFF",
        coreMid: "#4F46E5",
        coreOuter: "rgba(79, 70, 229, 0.6)",
        coreDeep: "rgba(49, 46, 129, 0.95)",
        glow: "rgba(79, 70, 229, 0.35)",
        ring: "rgba(99, 102, 241, 0.85)",
        particle: "rgba(129, 140, 248, 0.9)",
      },
      thinking: {
        coreCenter: "#FFFFFF",
        coreMid: "#7C3AED",
        coreOuter: "rgba(124, 58, 237, 0.65)",
        coreDeep: "rgba(76, 29, 149, 0.95)",
        glow: "rgba(124, 58, 237, 0.38)",
        ring: "rgba(147, 51, 234, 0.85)",
        particle: "rgba(168, 85, 247, 0.9)",
      },
      tool: {
        coreCenter: "#FFFFFF",
        coreMid: "#D97706",
        coreOuter: "rgba(217, 119, 6, 0.65)",
        coreDeep: "rgba(120, 53, 15, 0.95)",
        glow: "rgba(217, 119, 6, 0.32)",
        ring: "rgba(245, 158, 11, 0.85)",
        particle: "rgba(251, 191, 36, 0.9)",
      },
      confirmation: {
        coreCenter: "#FFFFFF",
        coreMid: "#EA580C",
        coreOuter: "rgba(234, 88, 12, 0.65)",
        coreDeep: "rgba(124, 45, 18, 0.95)",
        glow: "rgba(234, 88, 12, 0.38)",
        ring: "rgba(249, 115, 22, 0.85)",
        particle: "rgba(251, 146, 60, 0.9)",
      },
      executing: {
        coreCenter: "#FFFFFF",
        coreMid: "#2563EB",
        coreOuter: "rgba(217, 119, 6, 0.65)",
        coreDeep: "rgba(30, 58, 138, 0.95)",
        glow: "rgba(37, 99, 235, 0.35)",
        ring: "rgba(217, 119, 6, 0.85)",
        particle: "rgba(59, 130, 246, 0.85)",
      },
      speaking: {
        coreCenter: "#FFFFFF",
        coreMid: "#0284C7",
        coreOuter: "rgba(14, 165, 233, 0.65)",
        coreDeep: "rgba(12, 74, 110, 0.95)",
        glow: "rgba(2, 132, 199, 0.35)",
        ring: "rgba(14, 165, 233, 0.85)",
        particle: "rgba(56, 189, 248, 0.9)",
      },
      success: {
        coreCenter: "#FFFFFF",
        coreMid: "#059669",
        coreOuter: "rgba(5, 150, 105, 0.65)",
        coreDeep: "rgba(6, 78, 59, 0.95)",
        glow: "rgba(5, 150, 105, 0.35)",
        ring: "rgba(16, 185, 129, 0.85)",
        particle: "rgba(52, 211, 153, 0.9)",
      },
      error: {
        coreCenter: "#FFFFFF",
        coreMid: "#E11D48",
        coreOuter: "rgba(225, 29, 72, 0.65)",
        coreDeep: "rgba(136, 19, 55, 0.95)",
        glow: "rgba(225, 29, 72, 0.38)",
        ring: "rgba(244, 63, 94, 0.85)",
        particle: "rgba(251, 113, 133, 0.9)",
      },
    };

    this.darkStateColors = {
      idle: {
        coreCenter: "#FFFFFF",
        coreMid: "#00F0FF",
        coreOuter: "rgba(0, 163, 255, 0.35)",
        coreDeep: "rgba(4, 18, 38, 0.95)",
        glow: "rgba(0, 240, 255, 0.22)",
        ring: "rgba(0, 240, 255, 0.45)",
        particle: "rgba(0, 240, 255, 0.7)",
      },
      listening: {
        coreCenter: "#FFFFFF",
        coreMid: "#00F0FF",
        coreOuter: "rgba(0, 200, 255, 0.5)",
        coreDeep: "rgba(3, 24, 48, 0.95)",
        glow: "rgba(0, 240, 255, 0.38)",
        ring: "rgba(0, 240, 255, 0.75)",
        particle: "rgba(0, 240, 255, 0.85)",
      },
      hearing: {
        coreCenter: "#FFFFFF",
        coreMid: "#38BDF8",
        coreOuter: "rgba(14, 165, 233, 0.65)",
        coreDeep: "rgba(4, 30, 58, 0.95)",
        glow: "rgba(56, 189, 248, 0.5)",
        ring: "rgba(56, 189, 248, 0.9)",
        particle: "rgba(125, 211, 252, 0.9)",
      },
      processing: {
        coreCenter: "#FFFFFF",
        coreMid: "#6366F1",
        coreOuter: "rgba(99, 102, 241, 0.5)",
        coreDeep: "rgba(18, 16, 48, 0.95)",
        glow: "rgba(99, 102, 241, 0.35)",
        ring: "rgba(129, 140, 248, 0.7)",
        particle: "rgba(165, 180, 252, 0.8)",
      },
      thinking: {
        coreCenter: "#FFFFFF",
        coreMid: "#8B5CF6",
        coreOuter: "rgba(168, 85, 247, 0.6)",
        coreDeep: "rgba(25, 12, 54, 0.95)",
        glow: "rgba(139, 92, 246, 0.45)",
        ring: "rgba(192, 132, 252, 0.85)",
        particle: "rgba(216, 180, 254, 0.9)",
      },
      tool: {
        coreCenter: "#FFFFFF",
        coreMid: "#F59E0B",
        coreOuter: "rgba(217, 119, 6, 0.55)",
        coreDeep: "rgba(42, 22, 4, 0.95)",
        glow: "rgba(245, 158, 11, 0.4)",
        ring: "rgba(251, 191, 36, 0.8)",
        particle: "rgba(252, 211, 77, 0.85)",
      },
      confirmation: {
        coreCenter: "#FFFFFF",
        coreMid: "#FB923C",
        coreOuter: "rgba(234, 88, 12, 0.65)",
        coreDeep: "rgba(48, 18, 5, 0.95)",
        glow: "rgba(251, 146, 60, 0.5)",
        ring: "rgba(253, 186, 116, 0.9)",
        particle: "rgba(254, 215, 170, 0.9)",
      },
      executing: {
        coreCenter: "#FFFFFF",
        coreMid: "#3B82F6",
        coreOuter: "rgba(245, 158, 11, 0.6)",
        coreDeep: "rgba(10, 25, 48, 0.95)",
        glow: "rgba(59, 130, 246, 0.45)",
        ring: "rgba(245, 158, 11, 0.85)",
        particle: "rgba(96, 165, 250, 0.85)",
      },
      speaking: {
        coreCenter: "#FFFFFF",
        coreMid: "#06B6D4",
        coreOuter: "rgba(8, 145, 178, 0.65)",
        coreDeep: "rgba(4, 32, 44, 0.95)",
        glow: "rgba(6, 182, 212, 0.45)",
        ring: "rgba(34, 211, 238, 0.85)",
        particle: "rgba(103, 232, 249, 0.9)",
      },
      success: {
        coreCenter: "#FFFFFF",
        coreMid: "#10B981",
        coreOuter: "rgba(5, 150, 105, 0.65)",
        coreDeep: "rgba(3, 36, 24, 0.95)",
        glow: "rgba(16, 185, 129, 0.45)",
        ring: "rgba(52, 211, 153, 0.85)",
        particle: "rgba(110, 231, 183, 0.9)",
      },
      error: {
        coreCenter: "#FFFFFF",
        coreMid: "#EF4444",
        coreOuter: "rgba(220, 38, 38, 0.6)",
        coreDeep: "rgba(48, 8, 8, 0.95)",
        glow: "rgba(239, 68, 68, 0.45)",
        ring: "rgba(248, 113, 113, 0.85)",
        particle: "rgba(252, 165, 165, 0.9)",
      },
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
        radiusMult: 0.9 + Math.random() * 0.45,
        speed: (0.004 + Math.random() * 0.012) * (Math.random() > 0.5 ? 1 : -1),
        size: 1.0 + Math.random() * 2.2,
        alpha: 0.25 + Math.random() * 0.65,
        wobbleSpeed: 1 + Math.random() * 2,
      });
    }
  }

  resize() {
    if (!this.canvas) return;
    const rect = this.canvas.getBoundingClientRect();
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    this.width = rect.width;
    this.height = rect.height;
    this.canvas.width = this.width * dpr;
    this.canvas.height = this.height * dpr;
    this.ctx.scale(dpr, dpr);
    this.centerX = this.width / 2;
    this.centerY = this.height / 2;
    // Balanced baseRadius providing plenty of breathing room for expanding harmonics
    this.baseRadius = Math.min(this.width, this.height) * 0.26;
  }

  setState(state) {
    if (this.lightStateColors[state] || this.darkStateColors[state]) {
      this.state = state;
    }
  }

  setAudioLevel(level) {
    this.targetAudioLevel = Math.max(0.0, Math.min(1.0, level));
  }

  animate(currentTime) {
    const dt = Math.min((currentTime - this.lastFrameTime) / 1000, 0.1);
    this.lastFrameTime = currentTime;
    this.time += dt;

    // Smooth audio reactivity interpolation with decay
    this.audioLevel += (this.targetAudioLevel - this.audioLevel) * 0.22;

    this.render();
    requestAnimationFrame(this.animate);
  }

  render() {
    const ctx = this.ctx;
    if (!ctx) return;

    ctx.clearRect(0, 0, this.width, this.height);
    const isDark = document.documentElement.getAttribute("data-theme") === "dark";
    const palette = isDark ? this.darkStateColors : this.lightStateColors;
    const colors = palette[this.state] || palette.idle;

    // Subtle natural breathing oscillation (period: ~3.8 seconds)
    const breath = Math.sin(this.time * 1.65) * 0.035;
    const ampBoost = this.audioLevel * 0.35;
    let radius = this.baseRadius * (1 + breath + ampBoost);

    if (this.state === "listening") radius *= 1.05;
    if (this.state === "hearing") radius *= 1.10;
    if (this.state === "speaking") radius *= 1.08;

    // 1. Atmospheric Volumetric Back-Glow (Deep Diffusion)
    const glowRadius = radius * 1.70;
    const glowGrad = ctx.createRadialGradient(
      this.centerX, this.centerY, radius * 0.25,
      this.centerX, this.centerY, glowRadius
    );
    glowGrad.addColorStop(0, colors.glow);
    glowGrad.addColorStop(0.45, colors.glow.replace(/[\d.]+\)$/, "0.07)"));
    glowGrad.addColorStop(1, "transparent");

    ctx.fillStyle = glowGrad;
    ctx.beginPath();
    ctx.arc(this.centerX, this.centerY, glowRadius, 0, Math.PI * 2);
    ctx.fill();

    // 2. Swirling Quantum Micro-Particles
    this._renderParticles(ctx, radius, colors);

    // 3. State Specific Geometry / Rings
    if (this.state === "thinking") {
      this._renderThinkingCosmos(ctx, radius, colors);
    } else if (this.state === "tool" || this.state === "executing") {
      this._renderSegmentedTechRing(ctx, radius, colors);
    } else if (this.state === "speaking") {
      this._renderSpeakingHarmonics(ctx, radius, colors);
    } else {
      this._renderAmbientHarmonicRings(ctx, radius, colors);
    }

    // 4. Fluid Plasma Membrane Core (Liquid Mercury Deformation)
    this._renderFluidCore(ctx, radius, colors);

    // 5. Specular 3D Refraction Lens Highlight
    this._renderSpecularHighlight(ctx, radius);

    // 6. Delicate Equatorial Iris Ring
    ctx.save();
    ctx.strokeStyle = "rgba(255, 255, 255, 0.28)";
    ctx.lineWidth = 1.0;
    ctx.beginPath();
    ctx.ellipse(this.centerX, this.centerY, radius * 0.58, radius * 0.54, 0, 0, Math.PI * 2);
    ctx.stroke();
    ctx.restore();
  }

  _renderFluidCore(ctx, radius, colors) {
    const points = 72;
    const waveSpeed = this.state === "hearing" ? 4.5 : 2.2;
    const waveAmp = (this.state === "hearing" ? 12 : 3.5) + this.audioLevel * 16;

    ctx.save();
    ctx.shadowColor = colors.coreMid;
    ctx.shadowBlur = 24 + this.audioLevel * 28;

    // Volumetric 3D Gradient for Core Sphere
    const coreGrad = ctx.createRadialGradient(
      this.centerX - radius * 0.32,
      this.centerY - radius * 0.32,
      radius * 0.08,
      this.centerX,
      this.centerY,
      radius * 0.95
    );
    coreGrad.addColorStop(0, colors.coreCenter);
    coreGrad.addColorStop(0.25, colors.coreMid);
    coreGrad.addColorStop(0.65, colors.coreOuter);
    coreGrad.addColorStop(1.0, colors.coreDeep);

    ctx.fillStyle = coreGrad;
    ctx.beginPath();

    // Harmonic multi-node spline perimeter
    for (let i = 0; i <= points; i++) {
      const theta = (i / points) * Math.PI * 2;
      const wave1 = Math.sin(theta * 3 + this.time * waveSpeed) * waveAmp;
      const wave2 = Math.cos(theta * 5 - this.time * (waveSpeed * 0.7)) * (waveAmp * 0.45);
      const r = radius * 0.88 + wave1 + wave2;

      const x = this.centerX + Math.cos(theta) * r;
      const y = this.centerY + Math.sin(theta) * r;

      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    }
    ctx.closePath();
    ctx.fill();

    // Subtle edge rim light
    ctx.strokeStyle = colors.ring;
    ctx.lineWidth = 1.2;
    ctx.stroke();
    ctx.restore();
  }

  _renderSpecularHighlight(ctx, radius) {
    ctx.save();
    const specGrad = ctx.createRadialGradient(
      this.centerX - radius * 0.35,
      this.centerY - radius * 0.35,
      2,
      this.centerX - radius * 0.32,
      this.centerY - radius * 0.32,
      radius * 0.45
    );
    specGrad.addColorStop(0, "rgba(255, 255, 255, 0.75)");
    specGrad.addColorStop(0.4, "rgba(255, 255, 255, 0.2)");
    specGrad.addColorStop(1, "transparent");

    ctx.fillStyle = specGrad;
    ctx.beginPath();
    ctx.arc(this.centerX - radius * 0.32, this.centerY - radius * 0.32, radius * 0.45, 0, Math.PI * 2);
    ctx.fill();
    ctx.restore();
  }

  _renderParticles(ctx, radius, colors) {
    ctx.fillStyle = colors.particle;
    const speedMult = this.state === "thinking" ? 2.8 : this.state === "hearing" ? 1.8 : 1.0;

    for (let p of this.particles) {
      p.angle += p.speed * speedMult;
      const wobble = Math.sin(this.time * p.wobbleSpeed + p.angle) * 7;
      const r = radius * p.radiusMult + wobble;
      const x = this.centerX + Math.cos(p.angle) * r;
      const y = this.centerY + Math.sin(p.angle) * r;

      ctx.globalAlpha = p.alpha * (0.45 + this.audioLevel * 0.55);
      ctx.beginPath();
      ctx.arc(x, y, p.size, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.globalAlpha = 1.0;
  }

  _renderAmbientHarmonicRings(ctx, radius, colors) {
    const ringCount = 2;
    for (let i = 0; i < ringCount; i++) {
      const ringRadius = radius * (1.14 + i * 0.18);
      const dir = i % 2 === 0 ? 1 : -1;
      const rot = this.time * 0.75 * dir;

      ctx.save();
      ctx.strokeStyle = colors.ring;
      ctx.lineWidth = 1.2;
      ctx.beginPath();

      const segments = 64;
      for (let j = 0; j <= segments; j++) {
        const theta = (j / segments) * Math.PI * 2;
        const wave = Math.sin(theta * 6 + rot) * (2.5 + this.audioLevel * 9);
        const r = ringRadius + wave;
        const x = this.centerX + Math.cos(theta) * r;
        const y = this.centerY + Math.sin(theta) * r;
        if (j === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }
      ctx.stroke();
      ctx.restore();
    }
  }

  _renderThinkingCosmos(ctx, radius, colors) {
    ctx.save();
    // Inner Clockwise Luminous Arc
    ctx.strokeStyle = colors.ring;
    ctx.lineWidth = 2.2;
    ctx.shadowColor = colors.ring;
    ctx.shadowBlur = 12;
    ctx.beginPath();
    ctx.arc(this.centerX, this.centerY, radius * 1.16, this.time * 2.6, this.time * 2.6 + Math.PI * 1.35);
    ctx.stroke();

    // Outer Counter-Clockwise Arc
    ctx.strokeStyle = "rgba(192, 132, 252, 0.9)";
    ctx.lineWidth = 1.6;
    ctx.beginPath();
    ctx.arc(this.centerX, this.centerY, radius * 1.32, -this.time * 3.1, -this.time * 3.1 + Math.PI * 1.15);
    ctx.stroke();

    // Orbiting Spark Node
    const sparkAngle = this.time * 2.6 + Math.PI * 1.35;
    const sx = this.centerX + Math.cos(sparkAngle) * (radius * 1.16);
    const sy = this.centerY + Math.sin(sparkAngle) * (radius * 1.16);
    ctx.fillStyle = "#FFFFFF";
    ctx.beginPath();
    ctx.arc(sx, sy, 3.0, 0, Math.PI * 2);
    ctx.fill();
    ctx.restore();
  }

  _renderSegmentedTechRing(ctx, radius, colors) {
    ctx.save();
    ctx.strokeStyle = colors.ring;
    ctx.lineWidth = 2.0;
    const segments = 12;
    const step = (Math.PI * 2) / segments;
    const rot = this.time * 1.4;

    for (let i = 0; i < segments; i++) {
      if (i % 2 === 0) continue; // Alternate segmented HUD pattern
      const start = i * step + rot;
      const end = start + step * 0.72;
      ctx.beginPath();
      ctx.arc(this.centerX, this.centerY, radius * 1.22, start, end);
      ctx.stroke();
    }
    ctx.restore();
  }

  _renderSpeakingHarmonics(ctx, radius, colors) {
    const waveCount = 3;
    for (let i = 0; i < waveCount; i++) {
      const prog = (this.time * 1.15 + i * 0.33) % 1.0;
      const r = radius * (1.02 + prog * 0.52);
      const alpha = (1.0 - prog) * 0.75;

      ctx.save();
      ctx.strokeStyle = colors.ring.replace(/[\d.]+\)$/, `${alpha})`);
      ctx.lineWidth = 2.0 - prog * 1.2;
      ctx.beginPath();
      ctx.arc(this.centerX, this.centerY, r, 0, Math.PI * 2);
      ctx.stroke();
      ctx.restore();
    }
  }
}

window.VoiceOrb = VoiceOrb;
