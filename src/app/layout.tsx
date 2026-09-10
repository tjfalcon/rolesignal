import type { Metadata } from "next";

import "./globals.css";

export const metadata: Metadata = {
  title: "RoleSignal | Evidence-grounded job fit",
  description: "Compare job requirements with citation-backed candidate evidence without inventing experience.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
