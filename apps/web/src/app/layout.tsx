import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = { title: "Algo Trading Mentor", description: "Quant-research supervisor for your own trading rules." };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link href="https://fonts.googleapis.com/css2?family=Familjen+Grotesk:wght@400;500;600&family=Instrument+Serif:ital@0;1&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet" />
      </head>
      <body>
        {/* Theme bootstrap: an explicit choice stamps data-theme; "system" stamps nothing so prefers-color-scheme decides. */}
        <script dangerouslySetInnerHTML={{ __html: `try{var t=localStorage.getItem("theme");if(t==="dark"||t==="light")document.documentElement.setAttribute("data-theme",t);}catch(e){}` }} />
        {children}
      </body>
    </html>
  );
}
