import { useRef, useEffect } from 'react';

/**
 * CanvasMap — dark canvas with pulsing AQI markers, grid lines, road beziers, city labels.
 * Pure canvas, no Leaflet.
 */
export default function CanvasMap({ hotspots, conditionColor }) {
  const canvasRef = useRef(null);
  const animRef = useRef(null);
  const timeRef = useRef(0);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');

    const resize = () => {
      const rect = canvas.parentElement.getBoundingClientRect();
      const dpr = window.devicePixelRatio || 1;
      canvas.width = rect.width * dpr;
      canvas.height = rect.height * dpr;
      canvas.style.width = rect.width + 'px';
      canvas.style.height = rect.height + 'px';
      ctx.scale(dpr, dpr);
    };
    resize();
    window.addEventListener('resize', resize);

    // Project ward coords to canvas space
    const latMin = 28.48, latMax = 28.78;
    const lngMin = 77.0, lngMax = 77.35;

    const project = (lat, lng, w, h) => {
      const x = ((lng - lngMin) / (lngMax - lngMin)) * (w - 80) + 40;
      const y = ((latMax - lat) / (latMax - latMin)) * (h - 80) + 40;
      return [x, y];
    };

    const getMarkerColor = (aqi) => {
      if (aqi <= 50) return '#00c853';
      if (aqi <= 100) return '#92D14F';
      if (aqi <= 200) return '#FF7E00';
      if (aqi <= 300) return '#FF7E00';
      if (aqi <= 400) return '#FF0000';
      return '#99004C';
    };

    const animate = () => {
      timeRef.current++;
      const t = timeRef.current;
      const rect = canvas.parentElement.getBoundingClientRect();
      const w = rect.width;
      const h = rect.height;

      ctx.save();
      ctx.setTransform(window.devicePixelRatio || 1, 0, 0, window.devicePixelRatio || 1, 0, 0);

      // Dark background
      ctx.fillStyle = '#1a1f2e';
      ctx.fillRect(0, 0, w, h);

      // Grid lines
      ctx.strokeStyle = 'rgba(255,255,255,0.04)';
      ctx.lineWidth = 0.5;
      const gridSpacing = 40;
      for (let x = 0; x < w; x += gridSpacing) {
        ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, h); ctx.stroke();
      }
      for (let y = 0; y < h; y += gridSpacing) {
        ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(w, y); ctx.stroke();
      }

      // Faint road curves as bezier paths
      ctx.strokeStyle = 'rgba(255,255,255,0.06)';
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      ctx.moveTo(w * 0.1, h * 0.3);
      ctx.bezierCurveTo(w * 0.3, h * 0.15, w * 0.5, h * 0.5, w * 0.85, h * 0.25);
      ctx.stroke();
      ctx.beginPath();
      ctx.moveTo(w * 0.05, h * 0.7);
      ctx.bezierCurveTo(w * 0.25, h * 0.6, w * 0.6, h * 0.75, w * 0.95, h * 0.55);
      ctx.stroke();
      ctx.beginPath();
      ctx.moveTo(w * 0.4, h * 0.05);
      ctx.bezierCurveTo(w * 0.45, h * 0.35, w * 0.35, h * 0.65, w * 0.5, h * 0.95);
      ctx.stroke();

      // City labels
      const cityLabels = [
        { label: 'NEW DELHI', x: w * 0.48, y: h * 0.48 },
        { label: 'GURGAON', x: w * 0.3, y: h * 0.85 },
        { label: 'NOIDA', x: w * 0.78, y: h * 0.7 },
      ];
      ctx.font = '9px "JetBrains Mono", monospace';
      ctx.fillStyle = 'rgba(255,255,255,0.15)';
      ctx.textAlign = 'center';
      cityLabels.forEach(({ label, x, y }) => {
        ctx.fillText(label, x, y);
      });

      // Pulsing AQI markers
      hotspots.forEach((hotspot) => {
        const [x, y] = project(hotspot.lat, hotspot.lng, w, h);
        const color = getMarkerColor(hotspot.aqi);
        const pulsePhase = (t * 0.025) % (Math.PI * 2);
        const pulseScale = 1 + Math.sin(pulsePhase) * 0.35;

        // Outer ring 1 (pulsing)
        const outerR1 = 16 * pulseScale;
        ctx.beginPath();
        ctx.arc(x, y, outerR1, 0, Math.PI * 2);
        ctx.strokeStyle = color;
        ctx.globalAlpha = 0.15 + Math.sin(pulsePhase) * 0.1;
        ctx.lineWidth = 1;
        ctx.stroke();
        ctx.globalAlpha = 1;

        // Outer ring 2 (pulsing offset)
        const outerR2 = 12 * (1 + Math.sin(pulsePhase + 0.5) * 0.25);
        ctx.beginPath();
        ctx.arc(x, y, outerR2, 0, Math.PI * 2);
        ctx.strokeStyle = color;
        ctx.globalAlpha = 0.25 + Math.sin(pulsePhase + 0.5) * 0.1;
        ctx.lineWidth = 1;
        ctx.stroke();
        ctx.globalAlpha = 1;

        // Inner solid circle
        ctx.beginPath();
        ctx.arc(x, y, 7, 0, Math.PI * 2);
        ctx.fillStyle = color;
        ctx.globalAlpha = 0.85;
        ctx.fill();
        ctx.globalAlpha = 1;

        // AQI value inside
        ctx.font = 'bold 7px "JetBrains Mono", monospace';
        ctx.fillStyle = '#ffffff';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText(hotspot.aqi.toString(), x, y + 0.5);

        // Ward name below
        ctx.font = '8px "Inter", sans-serif';
        ctx.fillStyle = 'rgba(255,255,255,0.5)';
        ctx.fillText(hotspot.zone, x, y + 18);
      });

      ctx.restore();
      animRef.current = requestAnimationFrame(animate);
    };

    animRef.current = requestAnimationFrame(animate);

    return () => {
      window.removeEventListener('resize', resize);
      if (animRef.current) cancelAnimationFrame(animRef.current);
    };
  }, [hotspots, conditionColor]);

  return (
    <canvas
      ref={canvasRef}
      style={{ width: '100%', height: '100%', display: 'block', borderRadius: '12px' }}
    />
  );
}
