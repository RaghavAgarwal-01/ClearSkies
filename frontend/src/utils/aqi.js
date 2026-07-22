/**
 * AQI utilities — CPCB band classification & colors
 */

export const AQI_BANDS = [
  { min: 0,   max: 50,  label: 'Good',          key: 'good',          color: '#00E400' },
  { min: 51,  max: 100, label: 'Satisfactory',   key: 'satisfactory',  color: '#92D14F' },
  { min: 101, max: 200, label: 'Moderate',        key: 'moderate',      color: '#FFFF00' },
  { min: 201, max: 300, label: 'Poor',            key: 'poor',          color: '#FF7E00' },
  { min: 301, max: 400, label: 'Very Poor',       key: 'very-poor',     color: '#FF0000' },
  { min: 401, max: 500, label: 'Severe',          key: 'severe',        color: '#99004C' },
];

export function getBand(aqi) {
  const val = Math.round(aqi);
  for (const band of AQI_BANDS) {
    if (val >= band.min && val <= band.max) return band;
  }
  return AQI_BANDS[AQI_BANDS.length - 1];
}

export function getAqiColor(aqi) {
  return getBand(aqi).color;
}

export function getAqiBadgeClass(aqi) {
  return `aqi-badge-${getBand(aqi).key}`;
}

export function getAqiLabel(aqi) {
  return getBand(aqi).label;
}

/** Source attribution */
export const SOURCE_TYPES = {
  traffic:      { icon: '🚗', label: 'Traffic',      color: '#F5A623' },
  vehicular:    { icon: '🚗', label: 'Vehicular',    color: '#F5A623' },
  construction: { icon: '🏗', label: 'Construction',  color: '#FF7E00' },
  industrial:   { icon: '🏭', label: 'Industrial',    color: '#99004C' },
  agricultural: { icon: '🌾', label: 'Agricultural',  color: '#92D14F' },
  stubble_burning: { icon: '🌾', label: 'Stubble Burning', color: '#92D14F' },
  unknown:      { icon: '❔', label: 'Under review', color: '#94A3B8' },
};
