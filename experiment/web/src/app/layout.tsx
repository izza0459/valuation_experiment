import type { Metadata, Viewport } from "next";
import { Lato } from "next/font/google";
import "./globals.css";
import { QueryProvider } from "@/components/QueryProvider";

// The theme's typeface (the rebuild names Bayut's Mediator first; Lato is
// its open stand-in). Self-hosted by next/font, exposed as --font-sans.
const lato = Lato({
  variable: "--font-lato",
  subsets: ["latin"],
  weight: ["400", "700", "900"],
});

// Full-bleed on phones (the bottom tab bar sits above the home indicator).
export const viewport: Viewport = { width: "device-width", initialScale: 1, viewportFit: "cover", themeColor: "#ffffff" };

export const metadata: Metadata = {
  title: "Bayut Valuations",
  appleWebApp: { capable: true, title: "Bayut Valuations", statusBarStyle: "default" },
  icons: { icon: "/icons/icon-192.png", apple: "/icons/icon-192.png" },
  description: "In-house real estate valuation platform (Dubizzle Group / Bayut)",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  // Typography and page background come from the design system's tokens
  // (--font-sans is Lato, --surface-page the light grey), so no font or
  // colour classes are set here.
  // suppressHydrationWarning: browser extensions (Grammarly and the like) add
  // attributes to <html>/<body> before React loads. It applies to these two
  // tags' own attributes only, not to anything rendered inside them.
  return (
    <html lang="en" className={`${lato.variable} h-full antialiased`} suppressHydrationWarning>
      <body className="min-h-full" suppressHydrationWarning>
        <QueryProvider>{children}</QueryProvider>
      </body>
    </html>
  );
}
