"use client";

/**
 * A map of the property from the latitude and longitude on Property Address
 * (CRM feedback IN-08), shown on the Photos section. It moves when the
 * coordinates are edited. The report prints its own map from the same
 * coordinates (backend apps/reports/maps.py).
 *
 * Leaflet over plain map tiles, not OpenStreetMap's embed page: that one now
 * needs WebGL, which work laptops often have switched off.
 */

import { useEffect, useRef } from "react";
import "leaflet/dist/leaflet.css";

export function MapPreview({ latitude, longitude }: { latitude: unknown; longitude: unknown }) {
  const lat = Number(latitude);
  const lon = Number(longitude);
  const known = latitude !== null && latitude !== "" && longitude !== null && longitude !== "" && Number.isFinite(lat) && Number.isFinite(lon);

  return (
    <div style={{ marginBottom: 20 }}>
      <div style={{ fontSize: 15, fontWeight: 700, marginBottom: 6 }}>Location map</div>
      {known ? (
        <>
          <PropertyMap lat={lat} lon={lon} />
        </>
      ) : (
        <div style={{ fontSize: 14, color: "var(--text-muted)", padding: "14px 16px", borderRadius: 8, background: "var(--surface-subtle)" }}>
          Enter the latitude and longitude on Property Address and the map appears here and in the report.
        </div>
      )}
    </div>
  );
}

/** Leaflet is loaded in the browser only (it needs `window`). */
function PropertyMap({ lat, lon }: { lat: number; lon: number }) {
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let map: import("leaflet").Map | undefined;
    let cancelled = false;
    void import("leaflet").then((L) => {
      if (cancelled || !box.current) return;
      map = L.map(box.current, { scrollWheelZoom: false }).setView([lat, lon], 16);
      L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
        maxZoom: 19,
        attribution: "&copy; OpenStreetMap contributors",
      }).addTo(map);
      L.circleMarker([lat, lon], { radius: 9, weight: 3, color: "#fff", fillColor: "#006169", fillOpacity: 1 }).addTo(map);
    });
    return () => {
      cancelled = true;
      map?.remove();
    };
  }, [lat, lon]);

  return (
    <div
      ref={box}
      role="img"
      aria-label="Location map"
      style={{ height: 260, border: "1px solid var(--border-subtle)", borderRadius: 8, overflow: "hidden", zIndex: 0, position: "relative" }}
    />
  );
}
