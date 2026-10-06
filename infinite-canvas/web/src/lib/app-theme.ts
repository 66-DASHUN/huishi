import type { ThemeConfig } from "antd";
import { theme as antdTheme } from "antd";

const neutral = {
    light: {
        primary: "oklch(57% 0.24 265)",
        primaryHover: "oklch(51% 0.22 265)",
        primaryText: "#ffffff",
        menuBg: "oklch(95.5% 0.006 250)",
        menuText: "oklch(22% 0.008 250)",
        selectActiveBg: "oklch(95.5% 0.006 250)",
        selectSelectedBg: "oklch(95% 0.035 265)",
        selectText: "oklch(22% 0.008 250)",
        tableSelectedBg: "oklch(95% 0.035 265)",
        tableSelectedHoverBg: "oklch(92% 0.05 265)",
    },
    dark: {
        primary: "oklch(70% 0.15 265)",
        primaryHover: "oklch(76% 0.13 265)",
        primaryText: "#ffffff",
        menuBg: "oklch(25% 0.01 250)",
        menuText: "oklch(96% 0.003 250)",
        selectActiveBg: "oklch(25% 0.01 250)",
        selectSelectedBg: "oklch(27% 0.07 265)",
        selectText: "oklch(96% 0.003 250)",
        tableSelectedBg: "oklch(27% 0.07 265)",
        tableSelectedHoverBg: "oklch(31% 0.08 265)",
    },
};

export function getAntThemeConfig(dark: boolean): ThemeConfig {
    const color = dark ? neutral.dark : neutral.light;

    return {
        algorithm: dark ? antdTheme.darkAlgorithm : antdTheme.defaultAlgorithm,
        cssVar: { key: dark ? "infinite-canvas-dark" : "infinite-canvas-light" },
        token: {
            colorPrimary: color.primary,
            colorInfo: color.primary,
            colorLink: color.primary,
            colorLinkHover: color.primaryHover,
            colorLinkActive: color.primary,
            colorTextLightSolid: color.primaryText,
            borderRadius: 6,
            borderRadiusLG: 8,
            boxShadow: dark ? "none" : "0 4px 12px rgb(16 24 40 / 6%)",
        },
        components: {
            Button: {
                primaryShadow: "none",
            },
            Menu: {
                itemActiveBg: color.menuBg,
                itemHoverBg: color.menuBg,
                itemSelectedBg: color.menuBg,
                itemSelectedColor: color.menuText,
                darkItemHoverBg: neutral.dark.menuBg,
                darkItemSelectedBg: neutral.dark.menuBg,
                darkItemSelectedColor: neutral.dark.menuText,
            },
            Select: {
                optionActiveBg: color.selectActiveBg,
                optionSelectedBg: color.selectSelectedBg,
                optionSelectedColor: color.selectText,
            },
            Table: {
                rowSelectedBg: color.tableSelectedBg,
                rowSelectedHoverBg: color.tableSelectedHoverBg,
            },
        },
    };
}
