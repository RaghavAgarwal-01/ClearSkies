"""
overpass_pull.py
------------------
Pulls land-use (industrial/construction) and highway geometries from the
Overpass API (OpenStreetMap) for a bounding box -- feeds the Pollution
Attribution Agent's land-use features (construction_permit_density,
industrial_stack_count proxy) and the map's construction/industrial zone
overlays (Section 6 of the plan).

Reads the Overpass endpoint from the OVERPASS_URL environment variable
(see .env.example) so it can be pointed at a self-hosted instance or an
alternate mirror without a code change, falling back to the public
instance if unset.
"""

import os
import time

import requests
import geopandas as gpd
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

DEFAULT_OVERPASS_URL = "https://overpass-api.de/api/interpreter"
OVERPASS_URL = os.environ.get("OVERPASS_URL", DEFAULT_OVERPASS_URL)

# Overpass' public instance rate-limits / blocks requests with no
# identifying User-Agent -- polite and reduces silent throttling.
_HEADERS = {"User-Agent": "AirPulse/1.0 (ET AI Hackathon 2026 - air quality intervention platform)"}


def fetch_osm_features(bbox, amenity_type="industrial", max_retries: int = 3, timeout: int = 30) -> gpd.GeoDataFrame:
    """
    bbox format: (south, west, north, east)
    amenity_type: 'industrial', 'construction', or 'highway'

    Retries transient failures (timeouts, 5xx, rate limiting) with linear
    backoff -- Overpass' public instance is fair-use/free (Section 7 of
    the plan) and occasionally throttles under load, so a bare
    single-shot request is too brittle for a scheduled ingestion pull.
    """
    if amenity_type in ["industrial", "construction"]:
        query = f"""
        [out:json][timeout:25];
        (
          way["landuse"="{amenity_type}"]{bbox};
          relation["landuse"="{amenity_type}"]{bbox};
        );
        out geom;
        """
    elif amenity_type == "highway":
        query = f"""
        [out:json][timeout:25];
        (
          way["highway"~"motorway|trunk|primary|secondary"]{bbox};
        );
        out geom;
        """
    else:
        raise ValueError(
            f"Unknown amenity_type '{amenity_type}' -- expected 'industrial', "
            "'construction', or 'highway'."
        )

    response = None
    last_error = None
    for attempt in range(1, max_retries + 1):
        try:
            response = requests.post(
                OVERPASS_URL, data={"data": query}, headers=_HEADERS, timeout=timeout
            )
            if response.status_code == 200:
                break
            if response.status_code in (429, 504) and attempt < max_retries:
                # Rate-limited or gateway timeout -- back off and retry.
                time.sleep(2 * attempt)
                continue
            raise Exception(f"Overpass API error: {response.status_code} from {OVERPASS_URL}")
        except requests.exceptions.RequestException as e:
            last_error = e
            if attempt < max_retries:
                time.sleep(2 * attempt)
                continue
            raise Exception(f"Overpass API request failed after {max_retries} attempts: {last_error}") from e

    data = response.json()
    features = []

    for element in data.get("elements", []):
        if "geometry" in element:
            # Convert Overpass track to LineString or Polygon
            coords = [(pt["lon"], pt["lat"]) for pt in element["geometry"]]
            if len(coords) >= 2:
                features.append({
                    "type": "Feature",
                    "properties": {**element.get("tags", {}), "osm_id": str(element.get("id", ""))},
                    "geometry": {"type": "LineString", "coordinates": coords}
                })

    gdf = gpd.GeoDataFrame.from_features(features)
    if not gdf.empty:
        gdf.set_crs(epsg=4326, inplace=True)
    return gdf


# Quick cache utility for hackathon
if __name__ == "__main__":
    # Example Bounding box around Kanpur, India
    kanpur_bbox = (26.35, 80.20, 26.55, 80.40)
    print(f"Using Overpass endpoint: {OVERPASS_URL}")
    print("Fetching industrial zones...")
    ind_gdf = fetch_osm_features(kanpur_bbox, "industrial")
    ind_gdf.to_file("kanpur_industrial.geojson", driver="GeoJSON")
    print(f"Saved {len(ind_gdf)} industrial features.")
