import type { Metadata, Viewport } from 'next';
import type { ReactNode } from 'react';
import './globals.css';

export const metadata: Metadata = {
  title: 'HireAce Admin',
  description: 'Workstations, updates and OpenAI usage for HireAce',
  icons: { icon: '/logo.png' },
  robots: { index: false, follow: false },
};

export const viewport: Viewport = { themeColor: '#6d28d9', width: 'device-width', initialScale: 1 };

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link
          rel="stylesheet"
          href="https://fonts.googleapis.com/css2?family=Nunito+Sans:opsz,wght@6..12,400;6..12,500;6..12,600;6..12,700;6..12,800&display=swap"
        />
      </head>
      <body className="font-sans">{children}</body>
    </html>
  );
}
