import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { VitePWA } from "vite-plugin-pwa";

export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    {
      name: "watch-public-svg",
      configureServer(server) {
        server.watcher.add("public/**/*.svg");
        const notifySvgChange = (filePath: string) => {
          if (filePath.endsWith(".svg")) {
            server.ws.send({
              type: "custom",
              event: "public-svg-updated",
              data: { timestamp: Date.now(), file: filePath },
            });
          }
        };
        server.watcher.on("change", notifySvgChange);
        server.watcher.on("add", notifySvgChange);
        server.watcher.on("unlink", notifySvgChange);
      },
    },
    VitePWA({
      registerType: "autoUpdate",
      includeAssets: ["icon.svg", "MealSense_Logo.svg"],
      manifest: {
        name: "MealSense — mindful food logging",
        short_name: "MealSense",
        description: "Track meals and understand your nutrition.",
        theme_color: "#164c3b",
        background_color: "#f7f8f4",
        display: "standalone",
        start_url: "/",
        scope: "/",
        icons: [
          {
            src: "/icon-192.png",
            sizes: "192x192",
            type: "image/png",
            purpose: "any maskable",
          },
          {
            src: "/icon-512.png",
            sizes: "512x512",
            type: "image/png",
            purpose: "any maskable",
          },
        ],
      },
      workbox: {
        navigateFallback: "/index.html",
        globPatterns: ["**/*.{js,css,html,png}"],
        globIgnores: ["**/bg*.svg"],
        runtimeCaching: [],
      },
    } as any),
  ],
  server: {
    proxy: { "/api": { target: "http://127.0.0.1:8000", changeOrigin: true } },
  },
  preview: {
    proxy: { "/api": { target: "http://127.0.0.1:8000", changeOrigin: true } },
  },
});
