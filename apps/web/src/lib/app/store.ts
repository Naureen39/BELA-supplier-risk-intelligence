import { create } from "zustand";

export type Theme = "light" | "dark";

export interface Toast {
  id: number;
  tone: "info" | "success" | "error";
  text: string;
}

interface UiState {
  theme: Theme;
  setTheme: (t: Theme) => void;
  toasts: Toast[];
  toast: (tone: Toast["tone"], text: string) => void;
  dismiss: (id: number) => void;
  paletteOpen: boolean;
  setPalette: (v: boolean) => void;
}

function initialTheme(): Theme {
  try {
    const saved = localStorage.getItem("pr_theme");
    if (saved === "dark" || saved === "light") return saved;
    return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  } catch {
    return "light";
  }
}

let nextId = 1;

export const useUi = create<UiState>((set) => ({
  theme: "light",
  setTheme: (theme) => {
    try {
      localStorage.setItem("pr_theme", theme);
    } catch {
      /* storage unavailable: the choice lasts for this visit */
    }
    set({ theme });
  },
  toasts: [],
  toast: (tone, text) => {
    const id = nextId++;
    set((s) => ({ toasts: [...s.toasts.slice(-3), { id, tone, text }] }));
    setTimeout(() => set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })), 6000);
  },
  dismiss: (id) => set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })),
  paletteOpen: false,
  setPalette: (paletteOpen) => set({ paletteOpen }),
}));

export function loadTheme(): void {
  useUi.setState({ theme: initialTheme() });
}

/** Saved table views live in the browser: filters and visible columns per table. */
export interface SavedView {
  name: string;
  state: Record<string, unknown>;
}

export function readViews(key: string): SavedView[] {
  try {
    return JSON.parse(localStorage.getItem(`pr_views_${key}`) ?? "[]") as SavedView[];
  } catch {
    return [];
  }
}

export function writeViews(key: string, views: SavedView[]): void {
  try {
    localStorage.setItem(`pr_views_${key}`, JSON.stringify(views));
  } catch {
    /* storage unavailable */
  }
}
