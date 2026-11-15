import type { Config } from "tailwindcss";

export default {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: { sans: ["var(--font-sans)", "system-ui", "sans-serif"] },
      colors: {
        navy: { 50: "#f2f5fa", 100: "#e3e9f3", 200: "#c5d1e5", 300: "#9cb0d1", 400: "#6d88b6", 500: "#4c699c", 600: "#3a5282", 700: "#2f426a", 800: "#243352", 900: "#17223a", 950: "#0e1626" },
        series: { 1: "#2a78d6", 2: "#eb6834", 3: "#1baf7a" },
      },
      boxShadow: { card: "0 1px 2px rgba(16,24,40,.04), 0 1px 3px rgba(16,24,40,.06)" },
      keyframes: { "pulse-dot": { "0%,100%": { opacity: "1" }, "50%": { opacity: ".35" } } },
      animation: { "pulse-dot": "pulse-dot 1.4s ease-in-out infinite" },
    },
  },
  plugins: [],
} satisfies Config;
