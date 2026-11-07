import type { Metadata, Viewport } from "next";
import "./globals.css";
import "./neo.css";
import "./ux-pro.css";
import { AuthGate } from "../components/auth-gate";
export const metadata: Metadata = { title: "RevenueOS", description: "One operating system for business growth", applicationName: "RevenueOS", icons: {apple: "/icon-192.png", icon: "/icon-192.png"}, appleWebApp: {capable:true,title:"RevenueOS",statusBarStyle:"black-translucent"} };
export const viewport: Viewport = { width:"device-width", initialScale:1, themeColor:"#080b12" };
export default function Layout({children}:{children:React.ReactNode}) {
  return <html lang="en"><body><AuthGate>{children}</AuthGate></body></html>;
}
