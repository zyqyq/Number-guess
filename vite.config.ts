import { fileURLToPath, URL } from 'node:url'
import fs from 'node:fs'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// https://vite.dev/config/
// 语音通话依赖 getUserMedia，浏览器只在安全上下文（HTTPS / localhost）下开放。
// 开发模式若检测到 scripts/gen-cert.sh 生成的证书，则自动以 HTTPS 启动，
// 并把 /ws、/api 代理到 HTTP 后端，做到「页面 HTTPS、后端不用改」。

const certFile = fileURLToPath(new URL('./certs/server.crt', import.meta.url))
const keyFile = fileURLToPath(new URL('./certs/server.key', import.meta.url))

let httpsConfig: { key: Buffer; cert: Buffer } | false = false
if (fs.existsSync(certFile) && fs.existsSync(keyFile)) {
  httpsConfig = {
    key: fs.readFileSync(keyFile),
    cert: fs.readFileSync(certFile),
  }
}

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: httpsConfig
    ? {
        https: httpsConfig,
        host: true,
        port: 5173,
        proxy: {
          // WebSocket 需要 ws: true 才能升级
          '/ws': {
            target: 'http://127.0.0.1:8000',
            ws: true,
            changeOrigin: true,
          },
          '/api': {
            target: 'http://127.0.0.1:8000',
            changeOrigin: true,
          },
        },
      }
    : undefined,
})
