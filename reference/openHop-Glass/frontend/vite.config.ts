import { defineConfig, loadEnv } from "vite";
import vue from "@vitejs/plugin-vue";
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const proxyTarget = env.VITE_API_PROXY_TARGET || "http://localhost:8080";
  const appVersion = process.env.npm_package_version || env.VITE_APP_VERSION || "0.1.0";

  return {
    plugins: [vue()],
    define: {
      "import.meta.env.VITE_APP_VERSION": JSON.stringify(appVersion),
    },
    server: {
      port: 5173,
      proxy: {
        "/api": proxyTarget,
        "/healthz": proxyTarget,
      },
    },
  };
});

