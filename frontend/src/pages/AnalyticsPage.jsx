import { useEffect, useState } from 'react';
import { getAnalytics, getAlerts, getMultiCityComparison } from '../api/client';
import { IconBell } from '../components/Icons';

export default function AnalyticsPage() {
  const [analytics, setAnalytics] = useState(null);
  const [comparison, setComparison] = useState([]);
  const [alerts, setAlerts] = useState([]);
  const [error, setError] = useState('');

  useEffect(() => {
    Promise.all([
      getAnalytics(),
      getMultiCityComparison(),
      getAlerts().catch((err) => {
        console.warn('Unable to load alerts:', err);
        return [];
      }),
    ])
      .then(([summary, cities, recentAlerts]) => { setAnalytics(summary); setComparison(cities); setAlerts(recentAlerts); })
      .catch((err) => setError(err.message));
  }, []);

  if (error) return <div className="empty-state">Unable to load live analytics. {error}</div>;
  return <div className="fade-in">
    <div className="page-header"><h1 className="page-title">Analytics & Alerts</h1><p className="page-subtitle">Live enforcement outcomes, city benchmarks, and dispatched risk alerts</p></div>
    <div className="stats-grid">
      <div className="stat-card"><div className="stat-card-label">Interventions</div><div className="stat-card-value">{analytics?.total_interventions ?? '—'}</div></div>
      <div className="stat-card"><div className="stat-card-label">Average AQI drop</div><div className="stat-card-value">{analytics?.avg_aqi_drop ?? '—'}</div></div>
      <div className="stat-card"><div className="stat-card-label">Best action</div><div className="stat-card-value" style={{ fontSize: '1.1rem' }}>{analytics?.best_action_type || '—'}</div></div>
    </div>
    <div className="section-title">Multi-city comparison</div>
    <div className="card-static" style={{ padding: '16px', marginBottom: '24px' }}>
      {comparison.length ? comparison.map((city) => <div key={city.city} className="ward-row"><span className="ward-row-name">{city.city}</span><span>{city.avg_aqi} AQI · {city.intervention_count} interventions</span></div>) : <div className="empty-state">No multi-city data has been ingested yet.</div>}
    </div>
    <div className="section-title">Recent alerts</div>
    <div className="card-static" style={{ padding: '16px' }}>
      {alerts.length ? alerts.map((alert, index) => <div key={`${alert.dispatched_at}-${index}`} className="ward-row"><div><div className="ward-row-name">{alert.recipient} · {alert.risk_level}</div><div style={{ fontSize: '0.8rem', color: 'var(--color-text-muted)' }}>{alert.message}</div></div><span title="In-app alert" aria-label="In-app alert" style={{ display: 'inline-flex', color: 'var(--color-accent)' }}><IconBell width="18" height="18" /></span></div>) : <div className="empty-state">No alerts have been dispatched.</div>}
    </div>
  </div>;
}
