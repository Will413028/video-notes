export default {
  poweredByHeader: false,
  compress: false,
  async rewrites() {
    return [{ source: '/api/:path*', destination: 'http://127.0.0.1:8421/api/:path*' }]
  },
}
