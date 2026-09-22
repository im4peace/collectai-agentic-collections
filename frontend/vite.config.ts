/// <reference types="vitest/config" />
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Minimal config for E1-S5: dev server, build, and a Vitest unit-test
// environment. The `/api` dev proxy and design tokens are added by later
// UI stories (folder-structure.md's `frontend/` tree) once there is a real
// API to proxy to.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": "http://localhost:8000",
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
  },
});
