import { create } from "zustand";

export type ThemePreference = "system" | "light" | "dark";
export type ResolvedTheme = "light" | "dark";
export type ThemeName = ResolvedTheme;

export function resolveTheme(preference: ThemePreference, systemDark: boolean): ResolvedTheme {
    return preference === "system" ? (systemDark ? "dark" : "light") : preference;
}

function systemPrefersDark() {
    return typeof window !== "undefined" && window.matchMedia("(prefers-color-scheme: dark)").matches;
}

type ThemeStore = {
    preference: ThemePreference;
    resolvedTheme: ResolvedTheme;
    theme: ThemeName;
    setPreference: (preference: ThemePreference) => void;
    applyHostTheme: (preference: ThemePreference, resolvedTheme: ResolvedTheme) => void;
};

export const useThemeStore = create<ThemeStore>()((set) => ({
    preference: "system",
    resolvedTheme: "light",
    theme: "light",
    setPreference: (preference) => {
        const resolvedTheme = resolveTheme(preference, systemPrefersDark());
        set({ preference, resolvedTheme, theme: resolvedTheme });
    },
    applyHostTheme: (preference, resolvedTheme) => set({ preference, resolvedTheme, theme: resolvedTheme }),
}));
