/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        brand: {
          50: "#f0f5fb",
          100: "#dbe7f5",
          200: "#b9d1ea",
          300: "#8bb2da",
          400: "#578cc4",
          500: "#356fac",
          600: "#28568d",
          700: "#234672",
          800: "#213c5f",
          900: "#1f3450",
          950: "#141f33",
        },
        accent: {
          500: "#c8952b",
          600: "#a97620",
        },
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
      },
    },
  },
  plugins: [],
};
