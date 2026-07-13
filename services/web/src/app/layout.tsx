import type { Metadata } from "next";
import "./globals.css";
import { QueryProvider } from "@/components/query-provider";
import { ThemeProvider } from "@/components/theme/theme-provider";

export const metadata: Metadata = {
  title: "NIMB Ace · Research Platform",
  description: "NIMB Ace Capital — internal research platform for NEPSE.",
};

// Pre-hydration theme init — a plain inline <script> in <head> so it runs
// before first paint (no theme flash) AND lives at the same position in the
// server HTML and the client React tree. Using next/script beforeInteractive
// inside <body> caused a hydration mismatch because Next hoists it into <head>,
// shifting <body>'s first child. The <html> attributes it mutates are covered
// by suppressHydrationWarning below.
const THEME_INIT = `
try {
  var p = localStorage.getItem("nrc.theme");
  var r = (p === "dark" || p === "light") ? p : "dark";
  document.documentElement.setAttribute("data-theme", r);
  document.documentElement.style.colorScheme = r;
} catch (_) {}
`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_INIT }} />
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="" />
        <link
          href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&family=IBM+Plex+Sans:wght@300;400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&family=Newsreader:opsz,wght@6..72,400;6..72,500;6..72,600&family=Archivo:wght@400;500;600;700&display=swap"
          rel="stylesheet"
        />
      </head>
      <body suppressHydrationWarning>
        <div className="app-bg" aria-hidden />
        <ThemeProvider>
          <QueryProvider>{children}</QueryProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
