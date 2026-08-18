import "../styles/globals.css";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Driver Document Verification — Enterprise Microservices Dashboard",
  description: "Automated Driver KYC, OCR Extraction, and Identity Cross-Validation Suite",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
