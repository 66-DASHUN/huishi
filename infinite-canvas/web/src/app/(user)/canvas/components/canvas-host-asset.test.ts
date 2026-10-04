import { describe, expect, test } from "bun:test";

import { hostAssetToPickerAsset, hostAssetToInsertPayload, type HostCanvasLibraryAsset, type HostCanvasLibraryAssetDetail } from "./canvas-host-asset";

describe("host canvas asset conversion", () => {
    test("preserves audio media type and creates an audio insertion payload", () => {
        const asset: HostCanvasLibraryAsset = {
            id: 8,
            title: "旁白",
            image_path: "/static/uploads/voice.mp3",
            image_url: "https://huishi.example/static/uploads/voice.mp3",
            media_url: "https://huishi.example/static/uploads/voice.mp3",
            media_type: "speech",
            mime_type: "audio/mpeg",
            created_at: "2026-09-15T00:00:00Z",
            width: 0,
            height: 0,
        };
        const picker = hostAssetToPickerAsset(asset);
        expect(picker.kind).toBe("audio");
        expect(picker.mediaType).toBe("speech");

        const detail: HostCanvasLibraryAssetDetail = { ...asset, data_url: "data:audio/mpeg;base64,YQ==" };
        expect(hostAssetToInsertPayload(picker, detail)).toEqual({
            kind: "audio",
            url: detail.media_url,
            title: "旁白",
            mimeType: "audio/mpeg",
        });
    });
});
