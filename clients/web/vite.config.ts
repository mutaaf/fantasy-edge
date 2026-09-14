import { defineConfig } from "vite";

// The client is a renderer of the API, so in development the API is proxied
// under the same origin. POSTs to /api/replay then arrive from loopback, which
// is the only place the API accepts them from.
const api = process.env.FANTASYEDGE_API ?? "http://127.0.0.1:8793";

export default defineConfig({
  server: {
    host: "127.0.0.1",
    port: 5193,
    strictPort: true,
    proxy: { "/api": { target: api, changeOrigin: false } },
    fs: { allow: ["../.."] },
  },
  preview: {
    host: "127.0.0.1",
    port: 5194,
    proxy: { "/api": { target: api, changeOrigin: false } },
  },
  build: { target: "es2022", chunkSizeWarningLimit: 900 },
});
