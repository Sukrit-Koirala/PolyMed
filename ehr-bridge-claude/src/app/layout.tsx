import type { Metadata, Viewport } from "next";
import "./globals.css";
import { Providers } from "@/components/providers";

export const metadata: Metadata = {
  title: "EHR Bridge",
  description: "Your EHR holds the data. EHR Bridge makes that data usable. (Hackathon prototype — fictional data.)",
};

export const viewport: Viewport = { width: "device-width", initialScale: 1, themeColor: "#17223a" };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="font-sans" style={{ ["--font-sans" as string]: "Inter, 'Segoe UI', ui-sans-serif, system-ui, -apple-system, Roboto, sans-serif" }}>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
