import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Helix Trader",
  description: "A multilingual crypto futures trading bot platform.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="ko"
      className="h-full antialiased font-sans"
    >
      <body className="min-h-full bg-[#0B0E14] text-white flex flex-col font-sans">
        {children}
      </body>
    </html>
  );
}
