import type { Metadata } from "next";

import "./globals.css";
import "react-pdf/dist/Page/AnnotationLayer.css";
import "react-pdf/dist/Page/TextLayer.css";
import "yet-another-react-lightbox/styles.css";
import "vidstack/styles/base.css";
import "vidstack/styles/defaults.css";
import "vidstack/styles/community-skin/video.css";
import "vidstack/styles/community-skin/audio.css";

import { I18nProvider } from "@/components/i18n/i18n-provider";
import { DEFAULT_LOCALE, MESSAGES } from "@/i18n";

export const metadata: Metadata = {
  title: "ClawPilot",
  description: MESSAGES[DEFAULT_LOCALE].meta.description,
  icons: {
    icon: [
      { url: "/branding/clawpilot-mark.png", type: "image/png", sizes: "512x512" },
      { url: "/favicon.ico", sizes: "any" },
    ],
    apple: [{ url: "/apple-icon.png", sizes: "180x180", type: "image/png" }],
    shortcut: ["/favicon.ico"],
  },
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang={DEFAULT_LOCALE}>
      <body className="antialiased">
        <I18nProvider>{children}</I18nProvider>
      </body>
    </html>
  );
}
