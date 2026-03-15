import type { Metadata } from "next";
import "./globals.css";
import { Navbar } from "@/components/layout/Navbar";

export const metadata: Metadata = {
  title: "OpenClip — Turn YouTube videos into viral clips",
  description: "AI-powered local-first video clipping. Extract highlights, add captions, and resize for TikTok, Reels, and Shorts.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark" suppressHydrationWarning>
      <body>
        <div className="relative flex min-h-screen flex-col bg-black">
          <Navbar />
          <main className="flex-1">
            {children}
          </main>
        </div>
      </body>
    </html>
  );
}
