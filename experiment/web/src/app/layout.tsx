import type { Metadata } from "next";
import { Outfit } from "next/font/google";
import "./globals.css";
import { QueryProvider } from "@/components/QueryProvider";

// The design system's typeface. Loaded here (self-hosted by next/font)
// rather than via its fonts.css, and exposed to the tokens as --font-sans.
const outfit = Outfit({
  variable: "--font-outfit",
  subsets: ["latin"],
  weight: ["300", "400", "500", "600", "700"],
});

export const metadata: Metadata = {
  title: "dubizzle valuations",
  description: "In-house real estate valuation platform (Dubizzle Group / Bayut)",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  // Typography and page background come from the design system's tokens
  // (--font-sans is Outfit, --surface-page the light grey), so no font or
  // colour classes are set here.
  // suppressHydrationWarning: browser extensions (Grammarly and the like) add
  // attributes to <html>/<body> before React loads. It applies to these two
  // tags' own attributes only, not to anything rendered inside them.
  return (
    <html lang="en" className={`${outfit.variable} h-full antialiased`} suppressHydrationWarning>
      <body className="min-h-full" suppressHydrationWarning>
        <QueryProvider>{children}</QueryProvider>
      </body>
    </html>
  );
}
