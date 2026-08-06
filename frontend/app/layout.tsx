import type { Metadata } from "next";
import { headers } from "next/headers";
import "./globals.css";

export async function generateMetadata(): Promise<Metadata> {
  const incomingHeaders = await headers();
  const host =
    incomingHeaders.get("x-forwarded-host") ??
    incomingHeaders.get("host") ??
    "localhost:3000";
  const protocol =
    incomingHeaders.get("x-forwarded-proto") ??
    (host.startsWith("localhost") || host.startsWith("127.0.0.1") ? "http" : "https");
  const baseUrl = new URL(`${protocol}://${host}`);

  return {
    metadataBase: baseUrl,
    title: "Next Chapter — Powered by MemoryOS",
    description:
      "Turn player-confirmed squad memories into personal perspectives and a grounded mission to play next.",
    openGraph: {
      title: "Your squad has unfinished stories.",
      description:
        "MemoryOS turns a player-confirmed match into personal recalls and a new mission grounded in what actually happened.",
      type: "website",
      images: [{ url: "/og.png", width: 1672, height: 941, alt: "Your squad has unfinished stories" }],
    },
    twitter: {
      card: "summary_large_image",
      title: "Your squad has unfinished stories.",
      description: "Remember the match. Remix the roles. Reunite the squad.",
      images: ["/og.png"],
    },
  };
}

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
