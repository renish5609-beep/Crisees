import type { Metadata } from "next";
import "./globals.css";
import { Rail } from "@/components/Rail";
import { StatusBar } from "@/components/StatusBar";

export const metadata: Metadata = {
  title: "Crisees",
  description: "Flood evacuation accessibility planning for Houston / Harris County",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body className="min-h-dvh">
        <div className="grid min-h-dvh grid-cols-1 md:grid-cols-[13rem_1fr]">
          <Rail />
          <div className="flex min-w-0 flex-col">
            <StatusBar />
            <main className="flex-1">{children}</main>
          </div>
        </div>
      </body>
    </html>
  );
}
