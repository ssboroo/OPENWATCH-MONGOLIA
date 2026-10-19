import type { NextConfig } from 'next';
const backend = process.env.BACKEND_URL || 'http://backend:8000';
const config: NextConfig = {
 output: 'standalone',
 async rewrites() {
  return [
   {source:'/health',destination:`${backend}/health`},
   {source:'/api/:path*',destination:`${backend}/api/:path*`},
  ];
 },
 async headers() {
  return [{source:'/:path*',headers:[
   {key:'X-Content-Type-Options',value:'nosniff'},
   {key:'Referrer-Policy',value:'strict-origin-when-cross-origin'},
   {key:'X-Frame-Options',value:'DENY'},
   {key:'Permissions-Policy',value:'camera=(), microphone=(), geolocation=()'},
   {key:'Content-Security-Policy',value:"default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; img-src 'self' data: https:; connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'"},
  ]}];
 },
};
export default config;
