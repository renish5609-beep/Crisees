import type { Metadata, Viewport } from "next";
import "./globals.css";
import { Rail } from "@/components/Rail";
import { StatusBar } from "@/components/StatusBar";
import { WorkspaceProvider } from "@/lib/store";

export const metadata: Metadata = {
  title: "Crisees: Find the gaps. Plan the response.",
  description:
    "Equity-aware flood evacuation planning for southwest Houston: public data, network analysis and optimisation. A research and planning prototype.",
};

export const viewport: Viewport = { themeColor: "#0c1822", width: "device-width", initialScale: 1 };

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body className="min-h-dvh">
        <WorkspaceProvider>
          <div className="grid min-h-dvh grid-cols-1 lg:grid-cols-[14.5rem_1fr]">
            <Rail />
            <div className="flex min-w-0 flex-col lg:h-dvh">
              <StatusBar />
              <main className="min-h-0 flex-1">{children}</main>
            </div>
          </div>
        </WorkspaceProvider>
      </body>
    </html>
  );
}
