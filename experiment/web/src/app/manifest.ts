import type { MetadataRoute } from "next";

/** Lets phones install the site ("Add to Home Screen") and gives the Android
 * app its name, icon and colours. */
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "Bayut Valuations",
    short_name: "Valuations",
    description: "Bayut's valuation platform: instructions, inspections, valuations and reports.",
    start_url: "/login",
    display: "standalone",
    background_color: "#f4f5f6",
    theme_color: "#ffffff",
    icons: [
      { src: "/icons/icon-192.png", sizes: "192x192", type: "image/png" },
      { src: "/icons/icon-512.png", sizes: "512x512", type: "image/png" },
    ],
  };
}
