import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = { title: "Trader Console", description: "Trader environment and connection status." };

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}
