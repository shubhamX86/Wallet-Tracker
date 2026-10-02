import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: "#0a1220",
        panel: "#0f1b2d",
        panel2: "#13233a",
        line: "#1e3350",
        muted: "#7d93b0",
        teal: { DEFAULT: "#14b8a6", soft: "#0f766e" },
        cyan: { DEFAULT: "#22d3ee" },
        gain: "#22c55e",
        loss: "#ef4444",
      },
      fontFamily: { sans: ["Inter", "ui-sans-serif", "system-ui", "sans-serif"] },
    },
  },
  plugins: [],
};
export default config;
