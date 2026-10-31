import type { Metadata } from "next";
import "./globals.css";
import { AppShell } from "@/components/layout/app-shell";
import { AuthGate } from "@/components/auth-gate";

export const metadata: Metadata = {
  title: "CodePilot",
  description: "PR / Issue intelligent collaboration agent for engineering teams"
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN">
      <body>
        <AuthGate><AppShell>{children}</AppShell></AuthGate>
      </body>
    </html>
  );
}
