/** @type {import('tailwindcss').Config} */
export default {
  darkMode: ["class"],
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    container: {
      center: true,
      padding: "2rem",
      screens: {
        "2xl": "1400px",
      },
    },
    extend: {
      colors: {
        border: "hsl(var(--border, 24 15% 25%))",
        input: "hsl(var(--input, 24 15% 25%))",
        ring: "hsl(var(--ring, 18 85% 50%))",
        background: "hsl(var(--background, 24 50% 12%))",
        foreground: "hsl(var(--foreground, 42 60% 90%))",
        primary: {
          DEFAULT: "hsl(var(--primary, 18 85% 50%))",
          foreground: "hsl(var(--primary-foreground, 42 60% 95%))",
        },
        secondary: {
          DEFAULT: "hsl(var(--secondary, 24 35% 22%))",
          foreground: "hsl(var(--secondary-foreground, 42 60% 90%))",
        },
        destructive: {
          DEFAULT: "hsl(var(--destructive, 0 84.2% 60.2%))",
          foreground: "hsl(var(--destructive-foreground, 0 0% 98%))",
        },
        muted: {
          DEFAULT: "hsl(var(--muted, 24 25% 20%))",
          foreground: "hsl(var(--muted-foreground, 42 30% 70%))",
        },
        accent: {
          DEFAULT: "hsl(var(--accent, 36 90% 55%))",
          foreground: "hsl(var(--accent-foreground, 24 50% 12%))",
        },
        popover: {
          DEFAULT: "hsl(var(--popover, 24 45% 15%))",
          foreground: "hsl(var(--popover-foreground, 42 60% 90%))",
        },
        card: {
          DEFAULT: "hsl(var(--card, 24 45% 15%))",
          foreground: "hsl(var(--card-foreground, 42 60% 90%))",
        },
      },
      borderRadius: {
        lg: "var(--radius, 1rem)",
        md: "calc(var(--radius, 1rem) - 2px)",
        sm: "calc(var(--radius, 1rem) - 4px)",
      },
    },
  },
  plugins: [],
}
