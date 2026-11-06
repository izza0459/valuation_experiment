"use client";

/**
 * A map of the property from the latitude and longitude on Property Address
 * (CRM feedback IN-08), shown on the Photos section. It moves when the
 * coordinates are edited. The report prints its own map from the same
 * coordinates (backend apps/reports/maps.py).
 *
 * Drawn here with Leaflet rather than OpenStreetMap's embed page in a frame:
 * that page sized its map once, when it loaded, and if the workspace was still
 * laying out it drew only part of the map (or none), off-centre — the "loads
 * sometimes" bug. This one redraws whenever its box changes size.
 *
 * The view spans about 1.5 km so there are always streets around the pin, and
 * coordinates outside the UAE (usually swapped, or a digit off) are flagged.
 */

import { useEffect, useRef } from "react";
import "leaflet/dist/leaflet.css";

const ZOOM = 15;
// The UAE, roughly: anything outside is almost certainly a typo.
const UAE = { latMin: 22.5, latMax: 26.5, lonMin: 51.0, lonMax: 56.5 };

export function MapPreview({ latitude, longitude }: { latitude: unknown; longitude: unknown }) {
  const lat = Number(latitude);
  const lon = Number(longitude);
  const known = latitude !== null && latitude !== "" && longitude !== null && longitude !== "" && Number.isFinite(lat) && Number.isFinite(lon);
  const inUae = known && lat >= UAE.latMin && lat <= UAE.latMax && lon >= UAE.lonMin && lon <= UAE.lonMax;
  const swapped = known && !inUae && lon >= UAE.latMin && lon <= UAE.latMax && lat >= UAE.lonMin && lat <= UAE.lonMax;

  return (
    <div style={{ marginBottom: 20 }}>
      <div style={{ fontSize: 15, fontWeight: 700, marginBottom: 6 }}>Location map</div>
      {known ? (
        <>
          <PinMap lat={lat} lon={lon} />
          <div className="row wrap" style={{ justifyContent: "space-between", gap: 8, marginTop: 6, fontSize: 12.5, color: "var(--text-muted)" }}>
            <span className="num">{lat}, {lon}</span>
            <a href={`https://www.google.com/maps?q=${lat},${lon}`} target="_blank" rel="noopener noreferrer"
              style={{ color: "var(--accent)", textDecoration: "none" }}>
              Open in Google Maps
            </a>
          </div>
          {!inUae && (
            <div style={{ fontSize: 13, color: "var(--text-error)", marginTop: 6 }}>
              {swapped
                ? "These look swapped: latitude should be about 25 and longitude about 55 in Dubai. Fix them on Property Address."
                : "These coordinates are outside the UAE. Check the latitude and longitude on Property Address."}
            </div>
          )}
        </>
      ) : (
        <div style={{ fontSize: 14, color: "var(--text-muted)", padding: "14px 16px", borderRadius: 8, background: "var(--surface-subtle)" }}>
          Enter the latitude and longitude on Property Address and the map appears here and in the report.
        </div>
      )}
    </div>
  );
}

/** The map itself. Leaflet needs `window`, so it's loaded in the browser. */
function PinMap({ lat, lon }: { lat: number; lon: number }) {
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let map: import("leaflet").Map | undefined;
    let watcher: ResizeObserver | undefined;
    let cancelled = false;
    void import("leaflet").then((L) => {
      if (cancelled || !box.current) return;
      map = L.map(box.current, { scrollWheelZoom: false }).setView([lat, lon], ZOOM);
      L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
        maxZoom: 19,
        attribution: "&copy; OpenStreetMap contributors",
      }).addTo(map);
      // A pin drawn in CSS: Leaflet's own marker image doesn't survive bundling.
      L.marker([lat, lon], {
        icon: L.divIcon({ className: "map-pin", html: "<span></span>", iconSize: [26, 26], iconAnchor: [13, 26] }),
        keyboard: false,
      }).addTo(map);
      // Whenever the box changes size (the page still laying out, a column
      // opening, a phone turning), redraw and re-centre on the pin.
      watcher = new ResizeObserver(() => {
        map?.invalidateSize();
        map?.setView([lat, lon], map.getZoom(), { animate: false });
      });
      watcher.observe(box.current);
    });
    return () => {
      cancelled = true;
      watcher?.disconnect();
      map?.remove();
    };
  }, [lat, lon]);

  return (
    <div ref={box} role="img" aria-label={`Map of ${lat}, ${lon}`}
      style={{ height: 260, borderRadius: 8, overflow: "hidden", border: "1px solid var(--border-subtle)", position: "relative", zIndex: 0 }} />
  );
}
