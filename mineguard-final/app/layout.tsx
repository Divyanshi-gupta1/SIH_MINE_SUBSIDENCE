import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "MineGuard — Subsidence Control",
  description: "AI-enabled mine subsidence monitoring and early warning dashboard"
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return <html lang="en"><body>{children}</body></html>;
}
