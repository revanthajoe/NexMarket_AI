/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        brand: {
          50:  "#f0f4ff",
          100: "#e0eaff",
          200: "#c7d7fe",
          300: "#a5b8fd",
          400: "#8093fa",
          500: "#6366f1",
          600: "#4f46e5",
          700: "#4338ca",
          800: "#3730a3",
          900: "#312e81",
          950: "#1e1b4b",
        },
        surface: {
          DEFAULT: "#0f0e17",
          card:    "#17162a",
          border:  "#2d2b4e",
          muted:   "#1e1d35",
        },
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "monospace"],
      },
      backgroundImage: {
        "gradient-radial": "radial-gradient(var(--tw-gradient-stops))",
        "gradient-conic":  "conic-gradient(from 180deg at 50% 50%, var(--tw-gradient-stops))",
        "brand-gradient":  "linear-gradient(135deg, #6366f1, #8b5cf6, #06b6d4)",
        "dark-gradient":   "linear-gradient(180deg, #0f0e17 0%, #17162a 100%)",
      },
      animation: {
        "fade-in":    "fadeIn 0.5s ease-in-out",
        "slide-up":   "slideUp 0.4s ease-out",
        "pulse-slow": "pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite",
        "shimmer":    "shimmer 2s infinite",
        "glow":       "glow 2s ease-in-out infinite alternate",
      },
      keyframes: {
        fadeIn:  { from: { opacity: "0" }, to: { opacity: "1" } },
        slideUp: { from: { opacity: "0", transform: "translateY(20px)" }, to: { opacity: "1", transform: "translateY(0)" } },
        shimmer: { "0%": { backgroundPosition: "-200% 0" }, "100%": { backgroundPosition: "200% 0" } },
        glow:    { from: { boxShadow: "0 0 10px rgba(99,102,241,0.3)" }, to: { boxShadow: "0 0 25px rgba(99,102,241,0.7)" } },
      },
      boxShadow: {
        "brand":     "0 4px 24px rgba(99,102,241,0.35)",
        "card":      "0 2px 16px rgba(0,0,0,0.4)",
        "card-hover":"0 8px 32px rgba(99,102,241,0.2)",
      },
    },
  },
  plugins: [],
};
