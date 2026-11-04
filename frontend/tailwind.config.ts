import type { Config } from "tailwindcss";

/** rgb(var(--x) / <alpha-value>) so /opacity modifiers keep working */
const token = (name: string) => `rgb(var(--${name}) / <alpha-value>)`;

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // ── Editorial tokens ──────────────────────────────────
        paper: token("paper"),
        surface: token("surface"),
        sunken: token("sunken"),
        ink: {
          DEFAULT: token("ink"),
          secondary: token("ink-secondary"),
          tertiary: token("ink-tertiary"),
        },
        rule: {
          DEFAULT: token("rule"),
          strong: token("rule-strong"),
        },
        accent: {
          DEFAULT: token("accent"),
          hover: token("accent-hover"),
          foreground: token("on-accent"),
        },
        good: token("good"),
        warn: token("warn"),
        bad: token("bad"),

        // ── Legacy shadcn aliases ─────────────────────────────
        // Kept so pages not yet swept stay coherent. Remove once
        // the Phase 5 sweep reports zero usages.
        background: token("paper"),
        foreground: token("ink"),
        border: token("rule"),
        input: token("rule"),
        ring: token("accent"),
        card: { DEFAULT: token("surface"), foreground: token("ink") },
        muted: { DEFAULT: token("sunken"), foreground: token("ink-tertiary") },
        primary: { DEFAULT: token("accent"), foreground: token("on-accent") },
        secondary: { DEFAULT: token("accent"), foreground: token("on-accent") },
        destructive: { DEFAULT: token("bad"), foreground: token("on-accent") },
      },

      fontFamily: {
        sans: ["var(--font-sans)", "ui-sans-serif", "system-ui", "sans-serif"],
        serif: ["var(--font-serif)", "Georgia", "Times New Roman", "serif"],
      },

      // 12 / 13 / 14 / 16 / 20 / 28 / 34 / 40 / 48
      fontSize: {
        xs: ["12px", { lineHeight: "1.4" }],
        sm: ["13px", { lineHeight: "1.5" }],
        base: ["14px", { lineHeight: "1.55" }],
        lg: ["16px", { lineHeight: "1.5" }],
        xl: ["20px", { lineHeight: "1.3" }],
        "2xl": ["28px", { lineHeight: "1.2" }],
        "3xl": ["34px", { lineHeight: "1.15" }],
        "4xl": ["40px", { lineHeight: "1.1" }],
        "5xl": ["48px", { lineHeight: "1.05" }],
      },

      // Three weights. Anything louder collapses to 600.
      fontWeight: {
        light: "400",
        normal: "400",
        medium: "500",
        semibold: "600",
        bold: "600",
        extrabold: "600",
        black: "600",
      },

      // Clamped: residual rounded-2xl/3xl can't re-bubble the UI.
      borderRadius: {
        DEFAULT: "var(--radius)",
        sm: "2px",
        md: "var(--radius)",
        lg: "var(--radius-panel)",
        xl: "var(--radius-panel)",
        "2xl": "var(--radius-panel)",
        "3xl": "12px",
      },

      // Shadows exist only to lift modals and popovers off the page.
      boxShadow: {
        sm: "0 1px 2px rgb(16 16 16 / 0.04)",
        DEFAULT: "0 1px 2px rgb(16 16 16 / 0.04)",
        md: "0 1px 3px rgb(16 16 16 / 0.08)",
        lg: "0 4px 16px rgb(16 16 16 / 0.08)",
        xl: "0 4px 16px rgb(16 16 16 / 0.08)",
        "2xl": "0 8px 28px rgb(16 16 16 / 0.10)",
        none: "none",
      },
    },
  },
  plugins: [],
};

export default config;
