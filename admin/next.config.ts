import type { NextConfig } from 'next';

const nextConfig: NextConfig = {
  // The local database (used when DATABASE_URL is not set) loads its own files
  serverExternalPackages: ['@electric-sql/pglite'],
};

export default nextConfig;
