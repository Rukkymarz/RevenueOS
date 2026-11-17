/**
 * OKLCH tokens with real contrast measurement: OKLCH -> OKLab -> linear sRGB ->
 * WCAG relative luminance. Out-of-gamut colors are clipped before measuring.
 */
export interface Oklch { l: number; c: number; h: number }

export function parseOklch(css: string): Oklch {
  const m = /^oklch\(\s*([\d.]+)(%?)\s+([\d.]+)\s+([\d.]+)(?:deg)?\s*\)$/i.exec(css.trim());
  if (!m) throw new Error(`not an oklch() color: ${css}`);
  const l = parseFloat(m[1]!) / (m[2] === "%" ? 100 : 1);
  return { l, c: parseFloat(m[3]!), h: parseFloat(m[4]!) };
}

function oklchToLinearSrgb({ l, c, h }: Oklch): [number, number, number] {
  const hr = (h * Math.PI) / 180;
  const a = c * Math.cos(hr), b = c * Math.sin(hr);
  const l_ = l + 0.3963377774 * a + 0.2158037573 * b;
  const m_ = l - 0.1055613458 * a - 0.0638541728 * b;
  const s_ = l - 0.0894841775 * a - 1.291485548 * b;
  const L = l_ ** 3, M = m_ ** 3, S = s_ ** 3;
  const clip = (x: number) => Math.min(1, Math.max(0, x));
  return [
    clip(4.0767416621 * L - 3.3077115913 * M + 0.2309699292 * S),
    clip(-1.2684380046 * L + 2.6097574011 * M - 0.3413193965 * S),
    clip(-0.0041960863 * L - 0.7034186147 * M + 1.707614701 * S),
  ];
}

export function relativeLuminance(color: string | Oklch): number {
  const [r, g, b] = oklchToLinearSrgb(typeof color === "string" ? parseOklch(color) : color);
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

export function contrastRatio(fg: string, bg: string): number {
  const a = relativeLuminance(fg), b = relativeLuminance(bg);
  const [hi, lo] = a > b ? [a, b] : [b, a];
  return Math.round(((hi + 0.05) / (lo + 0.05)) * 100) / 100;
}

/** WCAG AA: 4.5:1 for body text, 3:1 for large text and UI components. */
export function meetsAA(fg: string, bg: string, kind: "text" | "large" | "ui" = "text"): boolean {
  return contrastRatio(fg, bg) >= (kind === "text" ? 4.5 : 3);
}

/** Base token set. Every color is OKLCH; pairs used together are checked in tests. */
export const tokens = {
  color: {
    bg: "oklch(0.99 0.003 250)",
    surface: "oklch(0.97 0.005 250)",
    fg: "oklch(0.22 0.02 255)",
    muted: "oklch(0.46 0.02 255)",
    accent: "oklch(0.52 0.16 255)",
    accentFg: "oklch(0.99 0.003 250)",
    danger: "oklch(0.52 0.19 27)",
    border: "oklch(0.88 0.01 250)",
  },
  radius: { sm: 6, md: 10, lg: 16, xl: 24 },
  space: { 1: 4, 2: 8, 3: 12, 4: 16, 6: 24, 8: 32, 12: 48, 16: 64 },
  /** Three-step vertical section rhythm (spec 9.6). */
  rhythm: { tight: 24, base: 48, loose: 96 },
} as const;

export const requiredPairs: Array<[keyof typeof tokens.color, keyof typeof tokens.color, "text" | "large" | "ui"]> = [
  ["fg", "bg", "text"], ["fg", "surface", "text"], ["muted", "bg", "text"], ["accentFg", "accent", "text"],
  ["danger", "bg", "text"], ["accent", "bg", "ui"],
];
