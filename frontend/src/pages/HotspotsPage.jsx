import { useState, useMemo, useEffect } from 'react';
import { MapContainer, TileLayer, CircleMarker, Tooltip } from 'react-leaflet';
import { getAqiColor, getAqiBadgeClass, getAqiLabel, SOURCE_TYPES } from '../utils/aqi';
import { postAttribution, getHotspotFeatures, getHotspots } from '../api/client';
import 'leaflet/dist/leaflet.css';

const FILTER_OPTIONS = [
  { key: 'all',          label: 'All Sources' },
  { key: 'traffic',      label: '🚗 Traffic' },
  { key: 'construction', label: '🏗 Construction' },
  { key: 'industrial',   label: '🏭 Industrial' },
  { key: 'stubble_burning', label: '🌾 Stubble burning' },
];

const ATTRIBUTION_FEATURES = [
  'traffic_density_idx',
  'construction_permit_density',
  'industrial_stack_count',
  'thermal_anomaly_count',
  'dust_landuse_pct',
  'pm25',
];

function hasCompleteAttributionFeatures(features) {
  return ATTRIBUTION_FEATURES.every((key) => (
    features[key] !== null
    && features[key] !== undefined
    && features[key] !== ''
    && Number.isFinite(Number(features[key]))
  ));
}

export default function HotspotsPage() {
  const [filter, setFilter] = useState('all');
  const [selectedId, setSelectedId] = useState(null);
  const [hotspots, setHotspots] = useState([]);
  const [isLoadingHotspots, setIsLoadingHotspots] = useState(true);

  useEffect(() => {
    let mounted = true;
    getHotspots()
      .then((data) => {
        if (mounted) {
          setHotspots(data || []);
          setIsLoadingHotspots(false);
        }
      })
      .catch((err) => {
        console.error("Failed to fetch hotspots", err);
        if (mounted) {
          setHotspots([]);
          setIsLoadingHotspots(false);
        }
      });
    return () => { mounted = false; };
  }, []);

  const filtered = useMemo(
    () => filter === 'all' ? hotspots : hotspots.filter((h) => h.source === filter),
    [filter, hotspots]
  );

  const selectedHotspot = hotspots.find((h) => h.id === selectedId);

  const [attribution, setAttribution] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);
  useEffect(() => {
    if (!selectedHotspot) {
      setAttribution(null);
      return;
    }
    
    let mounted = true;
    setIsLoading(true);
    setError(null);
    
    async function fetchAttr() {
      try {
        const features = await getHotspotFeatures(selectedHotspot.id);
        if (!hasCompleteAttributionFeatures(features)) {
          throw new Error('This hotspot does not yet have the observed data needed for AI attribution.');
        }
        const res = await postAttribution({ ...features, hotspot_id: Number(selectedHotspot.id) });
        if (mounted) {
          setAttribution(res);
          setIsLoading(false);
        }
      } catch (err) {
        if (mounted) {
          setError(err.message.startsWith('This hotspot')
            ? err.message
            : 'Attribution is temporarily unavailable. Please try again shortly.');
          setIsLoading(false);
        }
      }
    }
    
    fetchAttr();
    return () => { mounted = false; };
  }, [selectedHotspot]);

  return (
    <div className="fade-in">
      <div className="page-header">
        <h1 className="page-title">Hotspots & Attribution</h1>
        <p className="page-subtitle">
          Active pollution hotspots with AI-attributed source categories
        </p>
      </div>

      {/* Source-type toggle */}
      <div className="hotspot-filters">
        {FILTER_OPTIONS.map((opt) => (
          <button
            key={opt.key}
            className={`filter-btn${filter === opt.key ? ' active' : ''}`}
            onClick={() => setFilter(opt.key)}
          >
            {opt.label}
          </button>
        ))}
      </div>

      {/* Map */}
      <div className="map-container" style={{ marginBottom: '24px', position: 'relative' }}>
        {isLoadingHotspots && (
          <div style={{ position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, background: 'rgba(0,0,0,0.5)', zIndex: 1000, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#fff' }}>
            Loading live hotspots...
          </div>
        )}
        <MapContainer
          center={[28.6139, 77.2090]}
          zoom={11}
          style={{ height: '100%', width: '100%' }}
          scrollWheelZoom={true}
        >
          <TileLayer
            attribution='&copy; <a href="https://carto.com/">CARTO</a>'
            url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
          />
          {filtered.map((hotspot) => (
            <CircleMarker
              key={hotspot.id}
              center={[hotspot.lat, hotspot.lng]}
              radius={selectedId === hotspot.id ? 16 : hotspot.aqi > 300 ? 13 : 10}
              pathOptions={{
                color: getAqiColor(hotspot.aqi),
                fillColor: getAqiColor(hotspot.aqi),
                fillOpacity: selectedId === hotspot.id ? 0.8 : 0.4,
                weight: selectedId === hotspot.id ? 3 : 1.5,
                className: 'aqi-marker',
              }}
              eventHandlers={{
                click: () => setSelectedId(hotspot.id),
              }}
            >
              <Tooltip direction="top" offset={[0, -10]}>
                <div style={{ fontFamily: 'var(--font-body)', fontSize: '12px' }}>
                  <strong>{hotspot.zone}</strong><br />
                  {SOURCE_TYPES[hotspot.source]?.icon} {SOURCE_TYPES[hotspot.source]?.label} · AQI {hotspot.aqi}
                </div>
              </Tooltip>
            </CircleMarker>
          ))}
        </MapContainer>
      </div>

      {/* Hotspot list */}
      <div className="section-title">
        Active Hotspots
        <span style={{ fontWeight: 400, color: 'var(--color-text-muted)', marginLeft: '8px' }}>
          ({filtered.length})
        </span>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
        {isLoadingHotspots ? (
          <div className="empty-state">Loading live hotspots...</div>
        ) : filtered.length === 0 ? (
          <div className="empty-state">
            No hotspots detected for this source type in the last hour. Data refreshes every 15 minutes.
          </div>
        ) : (
          filtered.map((hotspot) => (
            <div
              key={hotspot.id}
              className={`hotspot-card${selectedId === hotspot.id ? ' selected' : ''}`}
              onClick={() => setSelectedId(hotspot.id)}
            >
              <div>
                <div className="hotspot-zone">{hotspot.zone}</div>
                <div className="hotspot-source" style={{ marginTop: '4px' }}>
                  {SOURCE_TYPES[hotspot.source]?.icon}{' '}
                  {SOURCE_TYPES[hotspot.source]?.label}
                </div>
              </div>

              <div style={{ textAlign: 'right' }}>
                <div style={{ fontSize: '0.625rem', color: 'var(--color-text-muted)', marginBottom: '4px' }}>
                  Confidence
                </div>
                <div className="confidence-bar">
                  <div
                    className="confidence-bar-fill"
                    style={{ width: `${hotspot.confidence}%` }}
                  />
                </div>
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.6875rem', color: 'var(--color-text-secondary)', marginTop: '2px' }}>
                  {hotspot.confidence}%
                </div>
              </div>

              <span className={`aqi-badge ${getAqiBadgeClass(hotspot.aqi)}`}>
                {getAqiLabel(hotspot.aqi)}
              </span>
              
              {/* Expand selected hotspot to show AI attribution */}
              {selectedId === hotspot.id && (
                <div style={{ gridColumn: '1 / -1', marginTop: '12px', paddingTop: '12px', borderTop: '1px solid var(--color-border)' }}>
                  <div style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--color-text-secondary)', marginBottom: '8px' }}>
                    {error ? 'Attribution status' : 'Live AI Attribution'}
                  </div>
                  {isLoading ? (
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: 'var(--color-text-muted)' }}>
                      <div style={{ animation: 'spin 1s linear infinite', height: '16px', width: '16px', border: '2px solid currentColor', borderRightColor: 'transparent', borderRadius: '50%' }} />
                      <span style={{ fontSize: '0.8125rem' }}>Analyzing features...</span>
                    </div>
                  ) : error ? (
                    <div style={{ color: 'var(--color-text-muted)', fontSize: '0.8125rem' }}>
                      {error}
                    </div>
                  ) : attribution ? (
                    <div>
                      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}>
                        <span style={{ fontSize: '0.8125rem', color: 'var(--color-text-primary)' }}>
                          Predicted: <strong>{SOURCE_TYPES[attribution.predicted_source]?.label || attribution.predicted_source}</strong>
                        </span>
                        <span style={{ fontSize: '0.8125rem', color: 'var(--color-accent)' }}>
                          {Math.round(attribution.confidence * 100)}% Conf
                        </span>
                      </div>
                      <div style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)', background: 'var(--color-bg-primary)', padding: '8px', borderRadius: '4px' }}>
                        <strong>Evidence:</strong> {Object.entries(attribution.evidence || {}).map(([key, value]) => `${key.replaceAll('_', ' ')}: ${value}`).join(' · ') || 'No feature explanation available.'}
                      </div>
                    </div>
                  ) : null}
                </div>
              )}
            </div>
          ))
        )}
      </div>
    </div>
  );
}
