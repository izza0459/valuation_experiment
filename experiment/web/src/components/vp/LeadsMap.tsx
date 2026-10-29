"use client";

/** Active leads on a map, one dot per lead, coloured by stage. Leaflet is
 * loaded in the browser only (it needs `window`). */

import { useEffect, useRef } from "react";
import "leaflet/dist/leaflet.css";

export type Pin = { id: number; ref: string; property: string; lat: number; lng: number; stage: string; community: string };

export const STAGE_COLOURS: Record<string, string> = {
  Setup: "#64748b",
  Scheduling: "#7c3aed",
  Inspection: "#d97706",
  Valuation: "#2563eb",
  Review: "#0d9488",
};

const DUBAI: [number, number] = [25.13, 55.2];

export function LeadsMap({ pins }: { pins: Pin[] }) {
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let map: import("leaflet").Map | undefined;
    let cancelled = false;
    void import("leaflet").then((L) => {
      if (cancelled || !box.current) return;
      map = L.map(box.current, { scrollWheelZoom: false }).setView(DUBAI, 10);
      L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
        maxZoom: 18,
        attribution: "&copy; OpenStreetMap contributors",
      }).addTo(map);
      const markers = pins.map((p) =>
        L.circleMarker([p.lat, p.lng], {
          radius: 8, weight: 2, color: "#fff", fillOpacity: 0.9, fillColor: STAGE_COLOURS[p.stage] ?? "#64748b",
        })
          .bindPopup(
            `<b>${escape(p.ref)}</b><br>${escape(p.property)}<br>${escape(p.stage)}<br><a href="/jobs/${p.id}">Open</a>`,
          )
          .addTo(map!),
      );
      if (markers.length) map.fitBounds(L.featureGroup(markers).getBounds(), { padding: [30, 30], maxZoom: 14 });
    });
    return () => {
      cancelled = true;
      map?.remove();
    };
  }, [pins]);

  return <div ref={box} style={{ height: 380, borderRadius: 10, overflow: "hidden", zIndex: 0, position: "relative" }} />;
}

function escape(text: string) {
  return text.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]!);
}
