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
    title: "Garena Next Chapter — MemoryOS",
    description:
      "Rediscover a squad memory, see your side of the story, and reunite for the next chapter.",
    openGraph: {
      title: "Your squad has unfinished stories.",
      description:
        "One shared memory. Your side of it. A new mission for the original squad.",
      type: "website",
      images: [{ url: "/og.png", width: 1672, height: 941, alt: "Your squad has unfinished stories" }],
    },
    twitter: {
      card: "summary_large_image",
      title: "Your squad has unfinished stories.",
      description: "One shared memory. Your side of it. A new mission for the original squad.",
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
