/**
 * API Client for ClearSkies (AirPulse) Backend
 * Wraps fetch calls to the FastAPI endpoints.
 */

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';

async function request(path, options = {}) {
  const url = `${API_BASE}${path}`;
  try {
    const res = await fetch(url, {
      headers: { 'Content-Type': 'application/json', ...options.headers },
      ...options,
    });
    if (!res.ok) {
      const errorBody = await res.text();
      throw new Error(`API ${res.status}: ${errorBody}`);
    }
    return await res.json();
  } catch (err) {
    if (err.name === 'TypeError' && err.message.includes('fetch')) {
      throw new Error('Backend is unreachable. Make sure the FastAPI server is running on ' + API_BASE);
    }
    throw err;
  }
}

// ---- Feature 10: Trends ----
export async function getAllTrends() {
  return request('/api/trends');
}

export async function getWardTrends(ward) {
  return request(`/api/trends/${encodeURIComponent(ward)}`);
}

// ---- Feature 2: Attribution ----
export async function postAttribution(hotspot) {
  return request('/api/attribution', {
    method: 'POST',
    body: JSON.stringify(hotspot),
  });
}

export async function getModelReport() {
  return request('/api/attribution/model-report');
}

// ---- Feature 5: Advisory ----
export async function postAdvisory(profile) {
  return request('/api/advisory', {
    method: 'POST',
    body: JSON.stringify(profile),
  });
}

// ---- Root health check ----
export async function getHealth() {
  return request('/');
}

// ---- Feature: Live Hotspots ----
export async function getHotspots() {
  return request('/api/hotspots');
}

export async function getWards() {
  return request('/api/wards');
}

export async function getForecast(ward) {
  return request(`/api/forecast/${encodeURIComponent(ward)}/multi-horizon`);
}

export async function getHotspotFeatures(id) {
  return request(`/api/hotspots/${encodeURIComponent(id)}/features`);
}

export async function getRecommendations(ward) {
  return request(`/api/recommendations/${encodeURIComponent(ward)}`);
}

export async function getHeatmap() {
  return request('/api/heatmap');
}

export async function getWardBoundaries() {
  return request('/api/wards/geojson');
}

export async function getAlerts() {
  return request('/api/alerts');
}

export async function getAnalytics() {
  return request('/api/analytics');
}

export async function getMultiCityComparison() {
  return request('/api/multi-city-comparison');
}

// ---- Feature: Admin Enforcement Queue ----
export async function getEnforcementQueue() {
  return request('/api/enforcement-queue');
}

export const postEnforcementOutcome = (data) =>
  request('/api/enforcement-outcome', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data)
  });

export const patchEnforcementStatus = (id, status) => request(`/api/enforcement/${encodeURIComponent(id)}`, {
  method: 'PATCH',
  body: JSON.stringify({ status }),
});

export const postChatQuery = (data) =>
  request('/api/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data)
  });
