import { useState, useMemo, useEffect } from 'react';
import {
  ResponsiveContainer, AreaChart, Area, Line, XAxis, YAxis,
  CartesianGrid, Tooltip as RechartsTooltip,
} from 'recharts';
import { HEALTH_IMPLICATIONS } from '../data/mockData';
import { getAqiColor, getAqiLabel, getBand } from '../utils/aqi';
import { getForecast, getWardTrends, getWards } from '../api/client';
import { useTheme } from '../hooks/useTheme';

const TIME_OPTIONS = ['24h', '48h', '72h'];

export default function ForecastPage() {
  const { theme } = useTheme();
  const [timeRange, setTimeRange] = useState('24h');
  const [wards, setWards] = useState([]);
  const [selectedWard, setSelectedWard] = useState('');
  const [forecastData, setForecastData] = useState([]);
  const wardName = selectedWard;
  const data = useMemo(() => forecastData.filter((point) => point.horizon_hr <= Number.parseInt(timeRange, 10)).map((point) => ({
    ...point, time: `+${point.horizon_hr}h`, predicted: point.predicted_aqi,
    lower: point.lower_bound, upper: point.upper_bound,
  })), [forecastData, timeRange]);
  const [trendData, setTrendData] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    let mounted = true;
    getWards().then((items) => {
      if (!mounted) return;
      setWards(items);
      setSelectedWard(items[0]?.name || '');
    }).catch((err) => { if (mounted) setError(err.message); });
    return () => { mounted = false; };
  }, []);

  useEffect(() => {
    let mounted = true;
    setIsLoading(true);
    setError(null);
    async function fetchTrend() {
      try {
        if (!wardName) return;
        const [res, forecast] = await Promise.all([getWardTrends(wardName), getForecast(wardName)]);
        if (mounted) {
          setTrendData(res);
          setForecastData(forecast);
          setIsLoading(false);
        }
      } catch (err) {
        if (mounted) {
          console.error("Failed to fetch trends", err);
          setError(err.message);
          setIsLoading(false);
          setTrendData(null);
        }
      }
    }
    fetchTrend();
    return () => { mounted = false; };
  }, [wardName]);

  const currentPredicted = data.length > 0 ? data[data.length - 1].predicted : 0;
  const band = getBand(currentPredicted);
  const severityColor = getAqiColor(currentPredicted);
  const implication = HEALTH_IMPLICATIONS[band.key] || '';
  const tickInterval = timeRange === '24h' ? 3 : timeRange === '48h' ? 6 : 12;

  // Theme-aware chart colors
  const isDark = theme === 'dark';
  const chartAccent = isDark ? '#38BDF8' : '#0EA5E9';
  const chartGrid = isDark ? 'rgba(100, 116, 139, 0.15)' : 'rgba(148, 163, 184, 0.2)';
  const chartTick = isDark ? '#64748B' : '#94A3B8';
  const chartAxis = isDark ? '#334155' : '#D5DDE6';
  const tooltipBg = isDark ? '#1E293B' : '#FFFFFF';
  const tooltipBorder = isDark ? '#334155' : '#D5DDE6';
  const tooltipText = isDark ? '#F1F5F9' : '#1E293B';
  const tooltipMuted = isDark ? '#64748B' : '#94A3B8';

  return (
    <div className="fade-in">
      <div className="page-header">
        <h1 className="page-title">AQI Forecast</h1>
        <p className="page-subtitle">
          AI-generated predictions with confidence intervals
        </p>
      </div>

      {/* Controls */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '16px', marginBottom: '24px', flexWrap: 'wrap' }}>
        <div className="pill-switcher">
          {TIME_OPTIONS.map((opt) => (
            <button
              key={opt}
              className={`pill-option${timeRange === opt ? ' active' : ''}`}
              onClick={() => setTimeRange(opt)}
            >
              {opt}
            </button>
          ))}
        </div>

        <div className="form-group" style={{ marginBottom: 0, minWidth: '200px' }}>
          <select
            className="form-select"
            value={selectedWard}
            onChange={(e) => setSelectedWard(e.target.value)}
          >
            {wards.map((w) => (
              <option key={w.name} value={w.name}>{w.name}</option>
            ))}
          </select>
        </div>
      </div>

      {/* Trend Data Section */}
      <div style={{ marginBottom: '24px' }}>
        {isLoading ? (
          <div style={{ animation: 'pulse 1.5s infinite', background: 'var(--color-bg-tertiary, rgba(128,128,128,0.2))', height: '100px', borderRadius: '8px', opacity: 0.5 }} />
        ) : error || !trendData ? (
          <div className="empty-state">Unable to load historical trend analysis. Showing baseline forecast.</div>
        ) : (
          <div className="stats-grid stagger">
            <div className="stat-card">
              <div className="stat-card-label">Avg AQI (Historical)</div>
              <div className="stat-card-value" style={{ color: getAqiColor(trendData.avg_aqi) }}>{trendData.avg_aqi}</div>
              <div className="stat-card-sub">Baseline for {wardName}</div>
            </div>
            <div className="stat-card">
              <div className="stat-card-label">Peak Month</div>
              <div className="stat-card-value" style={{ color: 'var(--color-warning)' }}>{trendData.peak_month}</div>
              <div className="stat-card-sub">Highest historical pollution</div>
            </div>
            <div className="stat-card">
              <div className="stat-card-label">Anomalies Detected</div>
              <div className="stat-card-value" style={{ color: 'var(--color-accent)' }}>{trendData.anomaly_days?.length || 0}</div>
              <div className="stat-card-sub">Days exceeding 2 stdev</div>
            </div>
          </div>
        )}
      </div>

      {/* Recharts line chart */}
      <div className="card-static" style={{ padding: '24px', marginBottom: '24px' }}>
        <div className="chart-container">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={data} margin={{ top: 10, right: 20, left: 0, bottom: 0 }}>
              <defs>
                <linearGradient id="confidenceFill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor={chartAccent} stopOpacity={0.15} />
                  <stop offset="95%" stopColor={chartAccent} stopOpacity={0.02} />
                </linearGradient>
              </defs>
              <CartesianGrid
                strokeDasharray="3 3"
                stroke={chartGrid}
                vertical={false}
              />
              <XAxis
                dataKey="time"
                tick={{ fill: chartTick, fontSize: 11, fontFamily: 'JetBrains Mono' }}
                axisLine={{ stroke: chartAxis }}
                tickLine={false}
                interval={tickInterval}
              />
              <YAxis
                tick={{ fill: chartTick, fontSize: 11, fontFamily: 'JetBrains Mono' }}
                axisLine={false}
                tickLine={false}
                domain={[0, 'auto']}
              />
              <RechartsTooltip
                contentStyle={{
                  background: tooltipBg,
                  border: `1px solid ${tooltipBorder}`,
                  borderRadius: '6px',
                  fontFamily: 'Inter',
                  fontSize: '12px',
                  color: tooltipText,
                  boxShadow: '0 4px 12px rgba(0,0,0,0.1)',
                }}
                labelStyle={{ color: tooltipMuted, marginBottom: '4px' }}
                formatter={(value, name) => {
                  const labels = { predicted: 'Predicted AQI', upper: 'Upper Bound', lower: 'Lower Bound' };
                  return [value, labels[name] || name];
                }}
              />
              {/* Confidence band */}
              <Area
                type="monotone"
                dataKey="upper"
                stroke="none"
                fill="url(#confidenceFill)"
                fillOpacity={1}
                isAnimationActive={false}
              />
              <Area
                type="monotone"
                dataKey="lower"
                stroke="none"
                fill={isDark ? '#0F172A' : '#F0F4F8'}
                fillOpacity={1}
                isAnimationActive={false}
              />
              {/* Prediction line */}
              <Line
                type="monotone"
                dataKey="predicted"
                stroke={chartAccent}
                strokeWidth={2}
                dot={false}
                activeDot={{ r: 4, fill: chartAccent, stroke: isDark ? '#0F172A' : '#FFFFFF', strokeWidth: 2 }}
                isAnimationActive={true}
                animationDuration={800}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* "What this means" panel */}
      <div className="severity-card" style={{ borderLeftColor: severityColor }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '10px' }}>
          <span className={`aqi-badge aqi-badge-${band.key}`}>
            {getAqiLabel(currentPredicted)}
          </span>
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.875rem', fontWeight: 600, color: severityColor }}>
            {currentPredicted} AQI
          </span>
        </div>
        <div className="section-title" style={{ marginBottom: '8px' }}>What this means</div>
        <p style={{ fontSize: '0.8125rem', color: 'var(--text-secondary)', lineHeight: 1.6 }}>
          {implication}
        </p>
      </div>
    </div>
  );
}
