import type { MetadataRoute } from "next";
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "RevenueOS — Revenue Operating System", short_name: "RevenueOS",
    description: "Business operations, leads, proposals, approvals and analytics",
    start_url: "/", display: "standalone", background_color: "#0b0e14", theme_color: "#0b0e14",
    icons: [{src:"/icon-192.png",sizes:"192x192",type:"image/png",purpose:"any"}, {src:"/icon-512.png",sizes:"512x512",type:"image/png",purpose:"any"}, {src:"/icon.svg",sizes:"any",type:"image/svg+xml",purpose:"any"}]
  };
}
