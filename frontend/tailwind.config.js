/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: "class",
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        brand: {
          50:  "#eff6ff",
          100: "#dbeafe",
          200: "#bfdbfe",
          300: "#93c5fd",
          400: "#60a5fa",
          500: "#3b82f6",
          600: "#2563eb",
          700: "#1d4ed8",
          800: "#1e40af",
          900: "#1e3a8a",
          950: "#172554",
        },
        surface: {
          DEFAULT: "#f4f8fb",
          card:    "#ffffff",
          border:  "#dce8ef",
          muted:   "#e9f1f5",
        },
        sidebar: {
          DEFAULT: "#0f172a",
          text: "#94a3b8",
          active: "#3b82f6",
        },
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "monospace"],
      },
      backgroundImage: {
        "gradient-radial": "radial-gradient(var(--tw-gradient-stops))",
        "gradient-conic":  "conic-gradient(from 180deg at 50% 50%, var(--tw-gradient-stops))",
        "brand-gradient":  "linear-gradient(135deg, #3b82f6, #06b6d4)",
        "light-gradient":  "linear-gradient(180deg, #f4f8fb 0%, #eef4f9 100%)",
      },
      animation: {
        "fade-in":    "fadeIn 0.4s ease-out forwards",
        "fade-in-up": "fadeInUp 0.4s cubic-bezier(0.16, 1, 0.3, 1) forwards",
        "slide-up":   "slideUp 0.4s ease-out forwards",
        "scale-up":   "scaleUp 0.3s cubic-bezier(0.16, 1, 0.3, 1) forwards",
        "pulse-slow": "pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite",
        "shimmer":    "shimmer 1.5s infinite",
      },
      keyframes: {
        fadeIn:    { from: { opacity: "0" },                           to: { opacity: "1" } },
        fadeInUp:  { from: { opacity: "0", transform: "translateY(8px)" }, to: { opacity: "1", transform: "translateY(0)" } },
        slideUp:   { from: { opacity: "0", transform: "translateY(16px)" }, to: { opacity: "1", transform: "translateY(0)" } },
        scaleUp:   { from: { opacity: "0", transform: "scale(0.96)" }, to: { opacity: "1", transform: "scale(1)" } },
        shimmer:   { "0%": { backgroundPosition: "-200% 0" }, "100%": { backgroundPosition: "200% 0" } },
      },
      boxShadow: {
        "brand":      "0 4px 16px rgba(59,130,246,0.25)",
        "card":       "0 1px 4px rgba(0,0,0,0.07), 0 1px 2px rgba(0,0,0,0.04)",
        "card-hover": "0 4px 20px rgba(59,130,246,0.12), 0 2px 8px rgba(0,0,0,0.06)",
        "sidebar":    "1px 0 0 #dce8ef",
      },
    },
  },
  plugins: [],
};
