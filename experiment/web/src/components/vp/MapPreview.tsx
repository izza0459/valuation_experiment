"use client";

/**
 * A map of the property from the latitude and longitude on Property Address
 * (CRM feedback IN-08), shown on the Photos section. It moves when the
 * coordinates are edited. The report prints its own map from the same
 * coordinates (backend apps/reports/maps.py).
 */

const SPAN_LAT = 0.004;
const SPAN_LON = 0.006;

export function MapPreview({ latitude, longitude }: { latitude: unknown; longitude: unknown }) {
  const lat = Number(latitude);
  const lon = Number(longitude);
  const known = latitude !== null && latitude !== "" && longitude !== null && longitude !== "" && Number.isFinite(lat) && Number.isFinite(lon);

  return (
    <div style={{ marginBottom: 20 }}>
      <div style={{ fontSize: 15, fontWeight: 700, marginBottom: 6 }}>Location map</div>
      {known ? (
        <>
          <iframe
            key={`${lat},${lon}`}
            title="Location map"
            src={`https://www.openstreetmap.org/export/embed.html?bbox=${lon - SPAN_LON},${lat - SPAN_LAT},${lon + SPAN_LON},${lat + SPAN_LAT}&layer=mapnik&marker=${lat},${lon}`}
            style={{ display: "block", width: "100%", height: 260, border: "1px solid var(--border-subtle)", borderRadius: 8 }}
          />
          <div style={{ fontSize: 13, color: "var(--text-muted)", marginTop: 4 }}>
            From the coordinates on Property Address ({lat}, {lon}). The report prints this map with a pin; no screenshot
            needed.
          </div>
        </>
      ) : (
        <div style={{ fontSize: 14, color: "var(--text-muted)", padding: "14px 16px", borderRadius: 8, background: "var(--surface-subtle)" }}>
          Enter the latitude and longitude on Property Address and the map appears here and in the report.
        </div>
      )}
    </div>
  );
}
