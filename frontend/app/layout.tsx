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
      "Turn verified match evidence into a player-reviewed memory, personal perspectives, and a verifiable mission to play next.",
    openGraph: {
      title: "Your squad has unfinished stories.",
      description:
        "Verified match evidence in. A grounded, player-reviewed next chapter out.",
      type: "website",
      images: [{ url: "/og.png", width: 1672, height: 941, alt: "Your squad has unfinished stories" }],
    },
    twitter: {
      card: "summary_large_image",
      title: "Your squad has unfinished stories.",
      description: "Facts in. Guarded intelligence. A verifiable next chapter out.",
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
