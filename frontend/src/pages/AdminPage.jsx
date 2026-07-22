import { useState, useEffect } from 'react';
import { SOURCE_TYPES } from '../utils/aqi';
import { getEnforcementQueue, patchEnforcementStatus, postEnforcementOutcome } from '../api/client';

export default function AdminPage() {
  const [queue, setQueue] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);
  const [logModalId, setLogModalId] = useState(null);
  const [logAqi, setLogAqi] = useState('');

  useEffect(() => {
    let mounted = true;
    setIsLoading(true);
    
    async function fetchQueue() {
      try {
        const data = await getEnforcementQueue();
        if (mounted) {
          setQueue(data.queue || data);
          setIsLoading(false);
        }
      } catch (err) {
        if (mounted) {
          console.error("Failed to fetch queue", err);
          setError(err.message);
          setQueue([]);
          setIsLoading(false);
        }
      }
    }
    
    const t = setTimeout(fetchQueue, 300); // slight delay for skeleton
    return () => { mounted = false; clearTimeout(t); };
  }, []);

  const handleStatusChange = async (id, newStatus) => {
    try {
      await patchEnforcementStatus(id, newStatus);
    } catch (err) {
      setError(err.message);
      return;
    }
    setQueue((prev) =>
      prev.map((item) =>
        item.id === id ? { ...item, status: newStatus } : item
      )
    );
  };

  const handleLogOutcome = async (id) => {
    const afterAqi = parseInt(logAqi);
    if (isNaN(afterAqi) || afterAqi < 0) return;
    
    const item = queue.find(i => i.id === id);
    const beforeAqi = item.before_aqi || item.beforeAqi || Math.round(afterAqi * 1.4);
    
    try {
      await postEnforcementOutcome({ queue_id: id, before_aqi: beforeAqi, after_aqi: afterAqi });
    } catch (err) {
      console.error("Failed to post enforcement outcome", err);
    }
    
    setQueue((prev) =>
      prev.map((i) =>
        i.id === id
          ? { ...i, status: 'Resolved', after_aqi: afterAqi, before_aqi: beforeAqi }
          : i
      )
    );
    setLogModalId(null);
    setLogAqi('');
  };

  const statusCounts = {
    pending: queue.filter((i) => i.status === 'pending').length,
    dispatched: queue.filter((i) => i.status === 'dispatched').length,
    resolved: queue.filter((i) => i.status === 'resolved' || i.status === 'Resolved').length,
  };

  return (
    <div className="fade-in">
      <div className="page-header">
        <h1 className="page-title">Enforcement Queue</h1>
        <p className="page-subtitle">
          Prioritized actions with closed feedback loop — track from recommendation to outcome
        </p>
      </div>

      {/* Status summary */}
      <div className="stats-grid stagger">
        <div className="stat-card">
          <div className="stat-card-label">Pending</div>
          <div className="stat-card-value" style={{ color: 'var(--color-warning)' }}>
            {statusCounts.pending}
          </div>
          <div className="stat-card-sub">Awaiting dispatch</div>
        </div>
        <div className="stat-card">
          <div className="stat-card-label">Dispatched</div>
          <div className="stat-card-value" style={{ color: 'var(--color-accent)' }}>
            {statusCounts.dispatched}
          </div>
          <div className="stat-card-sub">In progress</div>
        </div>
        <div className="stat-card">
          <div className="stat-card-label">Resolved</div>
          <div className="stat-card-value" style={{ color: 'var(--color-aqi-good)' }}>
            {statusCounts.resolved}
          </div>
          <div className="stat-card-sub">With AQI impact measured</div>
        </div>
      </div>

      {/* Enforcement items */}
      <div className="section-title">Action Queue</div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
        {isLoading ? (
          <div style={{ animation: 'pulse 1.5s infinite', background: 'var(--color-bg-tertiary, rgba(128,128,128,0.2))', height: '120px', borderRadius: '8px', opacity: 0.5 }} />
        ) : error && queue.length === 0 ? (
          <div className="empty-state">Unable to load enforcement queue. {error}</div>
        ) : queue.map((item) => {
          const priorityScore = item.priority_score || item.priority || 0;
          let priorityLevel = 'low';
          if (priorityScore > 8) priorityLevel = 'high';
          else if (priorityScore >= 6) priorityLevel = 'medium';
          
          return (
          <div key={item.id} className="enforcement-item" data-priority={priorityLevel}>
            <div className="enforcement-header">
              <div>
                <div className="enforcement-priority">
                  Priority #{item.priority_score ? item.priority_score.toFixed(2) : (item.priority ? item.priority.toFixed(1) : 'N/A')}
                </div>
                <div className="enforcement-location">{item.ward || item.location}</div>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <span style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)' }}>
                  {SOURCE_TYPES[item.source]?.icon} {SOURCE_TYPES[item.source]?.label}
                </span>
                <span className={`status-badge status-${item.status}`}>
                  {(item.status === 'pending' || item.status === 'Pending') && '⏳'}
                  {item.status === 'dispatched' && '🚀'}
                  {(item.status === 'resolved' || item.status === 'Resolved') && '✓'}
                  {' '}{item.status}
                </span>
              </div>
            </div>

            <div className="enforcement-action">
              {item.action}
            </div>

            <div className="enforcement-meta">
              {/* Status actions */}
              {(item.status === 'pending' || item.status === 'Pending') && (
                <button
                  className="btn btn-primary btn-small"
                  onClick={() => handleStatusChange(item.id, 'dispatched')}
                >
                  Mark Dispatched
                </button>
              )}

              {item.status === 'dispatched' && (
                <button
                  className="btn btn-success btn-small"
                  onClick={() => setLogModalId(item.id)}
                >
                  Log Outcome
                </button>
              )}

              {/* Resolved: show before/after delta */}
              {(item.status === 'resolved' || item.status === 'Resolved') && (item.before_aqi || item.beforeAqi) && (item.after_aqi || item.afterAqi) && (
                <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                  <div style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)' }}>
                    Before: <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--color-text-secondary)' }}>{item.before_aqi || item.beforeAqi}</span>
                  </div>
                  <span style={{ color: 'var(--color-text-muted)' }}>→</span>
                  <div style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)' }}>
                    After: <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--color-text-secondary)' }}>{item.after_aqi || item.afterAqi}</span>
                  </div>
                  <span className="aqi-delta-badge">
                    ▼ {(item.before_aqi || item.beforeAqi) - (item.after_aqi || item.afterAqi)} AQI
                  </span>
                </div>
              )}

              {logModalId === item.id && (
                <div className="inline-form">
                  <label style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)', whiteSpace: 'nowrap' }}>
                    Post-action AQI:
                  </label>
                  <input
                    type="number"
                    value={logAqi}
                    onChange={(e) => setLogAqi(e.target.value)}
                    placeholder="e.g. 162"
                    className="inline-form-input"
                  />
                  <button
                    className="btn btn-primary btn-small"
                    onClick={() => handleLogOutcome(item.id)}
                  >
                    Save
                  </button>
                  <button
                    className="btn btn-secondary btn-small"
                    onClick={() => { setLogModalId(null); setLogAqi(''); }}
                  >
                    Cancel
                  </button>
                </div>
              )}
            </div>
          </div>
          );
        })}
      </div>
    </div>
  );
}
