import type { ReactNode } from "react";
import "./globals.css";

export const metadata = { title: "RevenueOS Admin", description: "Registries, pins, budgets and kill switches" };

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen antialiased">{children}</body>
    </html>
  );
}
