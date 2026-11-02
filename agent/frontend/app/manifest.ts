import type { MetadataRoute } from 'next';

// Makes the web app installable on a phone ("Add to Home screen" / "Install app"):
// full screen with the HireAce icon, like an app. Phones keep the PC's link (the
// ?pc= cookie) and the access code, so it opens straight to this PC.
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: 'HireAce',
    short_name: 'HireAce',
    description: 'Talk to HireAce and approve what it does on your PC.',
    start_url: '/',
    scope: '/',
    display: 'standalone',
    orientation: 'portrait',
    background_color: '#0f172a',
    theme_color: '#0f172a',
    icons: [
      { src: '/icons/icon-192.png', sizes: '192x192', type: 'image/png', purpose: 'any' },
      { src: '/icons/icon-512.png', sizes: '512x512', type: 'image/png', purpose: 'any' },
      {
        src: '/icons/maskable-512.png',
        sizes: '512x512',
        type: 'image/png',
        purpose: 'maskable',
      },
    ],
  };
}
