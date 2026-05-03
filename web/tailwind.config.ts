import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Severity palette used by the issue badges
        severity: {
          critical: "#dc2626",
          important: "#ea580c",
          tip: "#2563eb",
        },
      },
    },
  },
  plugins: [],
};

export default config;
