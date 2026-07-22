import { useCondition } from './Layout';
import { CONDITIONS } from '../../data/conditionData';

export default function Topbar({ time, cityAqi }) {
  const { condition, conditionKey, setCondition } = useCondition();

  const formattedTime = time.toLocaleTimeString('en-IN', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  });

  return (
    <header className="topbar">
      {/* Left: brand (hidden on sidebar, but shown here for topbar spec) */}
      <div className="topbar-left">
        <div className="topbar-logo-mark">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="4" />
            <path d="M12 2v2" /><path d="M12 20v2" />
            <path d="m4.93 4.93 1.41 1.41" /><path d="m17.66 17.66 1.41 1.41" />
            <path d="M2 12h2" /><path d="M20 12h2" />
            <path d="m6.34 17.66-1.41 1.41" /><path d="m19.07 4.93-1.41 1.41" />
          </svg>
        </div>
        <div className="topbar-brand">
          <span className="topbar-brand-name">ClearSkies</span>
          <span className="topbar-brand-sub">Air Quality Intel</span>
        </div>
      </div>

      {/* Center: condition tabs */}
      <div className="condition-tabs">
        {CONDITIONS.map((c) => (
          <button
            key={c.key}
            className={`condition-tab${conditionKey === c.key ? ' active' : ''}`}
            onClick={() => setCondition(c.key)}
            aria-pressed={conditionKey === c.key}
            title={`Show live wards in the ${c.label} AQI band`}
          >
            {c.label}
          </button>
        ))}
      </div>

      {/* Right: AQI badge + time */}
      <div className="topbar-right">
        <span
          className="topbar-aqi-badge"
          style={{ color: condition.color }}
        >
          AQI {cityAqi !== null ? cityAqi : condition.aqi}
        </span>
        <span className="topbar-time">{formattedTime}</span>
      </div>
    </header>
  );
}
