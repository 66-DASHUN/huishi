import { create } from "zustand";

type CanvasHostSessionState = {
    requiresHostSession: boolean;
    loading: boolean;
    authenticated: boolean;
    userId: number | null;
    username: string;
    role: "user" | "admin" | "";
    billingIdentity: string;
    expiresAt: number | null;
    token: string;
    verifyUrl: string;
    assetsLibraryUrl: string;
    generateUrl: string;
    videoTasksUrl: string;
    chatUrl: string;
    projectsUrl: string;
    hostOrigin: string;
    imageModels: Array<{ id: string; label: string; resolutions: string[] }>;
    videoModels: Array<{ id: string; label: string }>;
    speechModels: Array<{ id: string; label: string }>;
    musicModels: Array<{ id: string; label: string }>;
    isGenerating: boolean;
    setStandalone: () => void;
    setLoading: (loading: boolean) => void;
    setGenerating: (isGenerating: boolean) => void;
    setSession: (payload: {
        userId: number;
        username: string;
        role: "user" | "admin";
        billingIdentity: string;
        expiresAt: number | null;
        token: string;
        verifyUrl: string;
        assetsLibraryUrl: string;
        generateUrl: string;
        videoTasksUrl: string;
        chatUrl: string;
        projectsUrl: string;
        hostOrigin: string;
        imageModels?: Array<{ id: string; label: string; resolutions: string[] }>;
        videoModels?: Array<{ id: string; label: string }>;
        speechModels?: Array<{ id: string; label: string }>;
        musicModels?: Array<{ id: string; label: string }>;
    }) => void;
    clearSession: () => void;
};

export const useCanvasHostSessionStore = create<CanvasHostSessionState>((set) => ({
    requiresHostSession: true,
    loading: true,
    authenticated: false,
    userId: null,
    username: "",
    role: "",
    billingIdentity: "",
    expiresAt: null,
    token: "",
    verifyUrl: "",
    assetsLibraryUrl: "",
    generateUrl: "",
    videoTasksUrl: "",
    chatUrl: "",
    projectsUrl: "",
    hostOrigin: "",
    imageModels: [],
    videoModels: [],
    speechModels: [],
    musicModels: [],
    isGenerating: false,
    setStandalone: () =>
        set({
            requiresHostSession: false,
            loading: false,
            authenticated: false,
            userId: null,
            username: "",
            role: "",
            billingIdentity: "",
            expiresAt: null,
            token: "",
            verifyUrl: "",
            assetsLibraryUrl: "",
            generateUrl: "",
            videoTasksUrl: "",
            chatUrl: "",
            projectsUrl: "",
            hostOrigin: "",
            imageModels: [],
            videoModels: [],
            speechModels: [],
            musicModels: [],
            isGenerating: false,
        }),
    setLoading: (loading) => set({ loading }),
    setGenerating: (isGenerating) => set({ isGenerating }),
    setSession: (payload) =>
        set({
            requiresHostSession: true,
            loading: false,
            authenticated: true,
            userId: payload.userId,
            username: payload.username,
            role: payload.role,
            billingIdentity: payload.billingIdentity,
            expiresAt: payload.expiresAt,
            token: payload.token,
            verifyUrl: payload.verifyUrl,
            assetsLibraryUrl: payload.assetsLibraryUrl,
            generateUrl: payload.generateUrl,
            videoTasksUrl: payload.videoTasksUrl,
            chatUrl: payload.chatUrl,
            projectsUrl: payload.projectsUrl,
            hostOrigin: payload.hostOrigin,
            imageModels: payload.imageModels || [],
            videoModels: payload.videoModels || [],
            speechModels: payload.speechModels || [],
            musicModels: payload.musicModels || [],
        }),
    clearSession: () =>
        set({
            requiresHostSession: true,
            loading: false,
            authenticated: false,
            userId: null,
            username: "",
            role: "",
            billingIdentity: "",
            expiresAt: null,
            token: "",
            verifyUrl: "",
            assetsLibraryUrl: "",
            generateUrl: "",
            videoTasksUrl: "",
            chatUrl: "",
            projectsUrl: "",
            hostOrigin: "",
            imageModels: [],
            videoModels: [],
            speechModels: [],
            musicModels: [],
            isGenerating: false,
        }),
}));
