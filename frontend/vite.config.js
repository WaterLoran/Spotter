import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 3000,
    // 默认只绑 IPv6(::1) 时，用 127.0.0.1 打开会连接失败；true 同时监听 IPv4/IPv6
    host: true,
    strictPort: true,
    proxy: {
      "/api": {
        // start.sh 默认 PORT=5001；直接跑 python 且未设 PORT 时为 backend/config.py 的 5000，需设 VITE_API_PROXY=http://127.0.0.1:5000 npm run dev
        target: process.env.VITE_API_PROXY || "http://127.0.0.1:5001",
        changeOrigin: true,
        timeout: 120000,
        proxyTimeout: 120000
      }
    }
  }
});

