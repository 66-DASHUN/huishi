import { requestMusicGeneration, type AudioGenerationResult, type AudioRequestOptions } from "./audio";
import type { AiConfig } from "@/stores/use-config-store";

/** 独立的音乐入口，避免把音乐参数误传到语音合成请求。 */
export function generateMusic(config: AiConfig, prompt: string, options?: AudioRequestOptions): Promise<AudioGenerationResult> {
    return requestMusicGeneration(config, prompt, options);
}
