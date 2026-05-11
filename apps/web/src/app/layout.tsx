import type { Metadata } from "next";
import "./globals.css";

/**
 * Root layout — applies once per page, wraps every route.
 *
 * The metro-scoped top nav (F-NAV-01: `Areas | Timing | Compare | Map | Saved
 * | Learn`) lives one level deeper at `(metro)/[metro]/layout.tsx` so that
 * marketing/education/account routes can opt out.
 */

export const metadata: Metadata = {
  title: {
    default: "Bay Area RE",
    template: "%s · Bay Area RE",
  },
  description:
    "Decision-support for first-time home buyers in the Bay Area: affordability, school zones, market timing, and a 'what changed' alert feed.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" data-theme="dark">
      <body className="bg-bg text-tx min-h-screen">{children}</body>
    </html>
  );
}
