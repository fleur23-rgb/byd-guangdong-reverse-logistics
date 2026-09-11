import type { NextConfig } from 'next';

const isGitHubPages = process.env.GITHUB_PAGES === 'true';

const nextConfig: NextConfig = {
  output: isGitHubPages ? 'export' : undefined,
  assetPrefix: isGitHubPages ? '/china-ev-battery-reverse-logistics' : undefined,
  trailingSlash: isGitHubPages,
};

export default nextConfig;
