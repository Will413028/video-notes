import type { NextConfig } from 'next'

const backendOrigin = process.env.VIDEO_NOTES_BACKEND_ORIGIN ?? 'http://127.0.0.1:8422'

const config: NextConfig = {
  poweredByHeader: false,
  compress: false,
  async rewrites() {
    return [{ source: '/api/:path*', destination: `${backendOrigin}/api/:path*` }]
  },
}

export default config
