import { useEffect, useState } from 'react';
import { CircleMarker, GeoJSON, MapContainer, TileLayer, Tooltip } from 'react-leaflet';
import { getHeatmap, getWardBoundaries } from '../api/client';
import { getAqiColor } from '../utils/aqi';
import 'leaflet/dist/leaflet.css';

export default function LiveMap({ hotspots = [] }) {
  const [heatmap, setHeatmap] = useState([]);
  const [boundaries, setBoundaries] = useState(null);

  useEffect(() => {
    let active = true;
    Promise.all([getHeatmap(), getWardBoundaries()]).then(([heat, wards]) => {
      if (!active) return;
      setHeatmap(heat.grid || []);
      setBoundaries(wards);
    }).catch(() => {});
    return () => { active = false; };
  }, []);

  return (
    <MapContainer center={[28.6139, 77.2090]} zoom={11} style={{ height: '100%', width: '100%' }} scrollWheelZoom>
      <TileLayer attribution='&copy; <a href="https://carto.com/">CARTO</a>' url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png" />
      {boundaries && <GeoJSON data={boundaries} style={() => ({ color: '#38BDF8', weight: 1, fillOpacity: 0.04 })} />}
      {heatmap.map((point, index) => (
        <CircleMarker key={`${point.lat}-${point.lon}-${index}`} center={[point.lat, point.lon]}
          radius={10} pathOptions={{ stroke: false, fillColor: getAqiColor(point.value), fillOpacity: 0.08 }} />
      ))}
      {hotspots.map((hotspot) => (
        <CircleMarker key={hotspot.id} center={[hotspot.lat, hotspot.lng]} radius={hotspot.aqi > 300 ? 11 : 8}
          pathOptions={{ color: getAqiColor(hotspot.aqi), fillColor: getAqiColor(hotspot.aqi), fillOpacity: 0.75, weight: 2 }}>
          <Tooltip><strong>{hotspot.zone}</strong><br />AQI {hotspot.aqi}</Tooltip>
        </CircleMarker>
      ))}
    </MapContainer>
  );
}
