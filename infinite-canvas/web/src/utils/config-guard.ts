import { useConfigStore } from "@/stores/use-config-store";
import { useRouter } from "next/navigation";
import { message } from "antd";

/**
 * 检测是否配置了有效的API Key
 */
export function hasValidApiConfig(): boolean {
    const config = useConfigStore.getState().config;

    // 检查是否有至少一个渠道且有有效的API Key
    const hasValidChannel = config.channels.some((ch) => ch.apiKey && ch.apiKey.trim().length > 0 && ch.apiKey !== "placeholder" && !ch.apiKey.includes("your-api-key"));

    return hasValidChannel;
}

/**
 * 引导用户到设置页
 * @param highlightTab - 高亮的Tab ID（channels, models, agent等）
 */
export function redirectToSettings(highlightTab: string = "channels") {
    if (typeof window === "undefined") return;

    const params = highlightTab ? `?tab=${highlightTab}` : "";

    message.warning("请先配置API Key以使用AI功能");
    window.location.href = `/settings${params}`;
}

/**
 * Hook: 在组件中使用的配置检测
 */
export function useConfigGuard() {
    const router = useRouter();

    const checkAndRedirect = (highlightTab: string = "channels"): boolean => {
        if (!hasValidApiConfig()) {
            redirectToSettings(highlightTab);
            return false;
        }
        return true;
    };

    return { hasValidApiConfig, checkAndRedirect };
}
