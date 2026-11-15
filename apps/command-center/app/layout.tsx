import type { ReactNode } from "react";
import "./globals.css";

export const metadata = { title: "RevenueOS Command Center", description: "Human-controlled orchestration console" };

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen antialiased">{children}</body>
    </html>
  );
}
