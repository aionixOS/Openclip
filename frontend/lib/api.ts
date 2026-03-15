import { Project, Clip, Settings, CaptionStyle } from './types';

function getBaseUrl(): string {
    if (typeof window !== 'undefined') {
        const host = window.location.hostname;
        if (host !== 'localhost' && host !== '127.0.0.1') {
            return `https://${host.replace(/^(\d+)-/, '8000-')}`;
        }
    }
    return process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
}

export function getApiBaseUrl(): string {
    return getBaseUrl();
}

export const getProjects = async (): Promise<Project[]> => {
    const res = await fetch(`${getBaseUrl()}/api/projects`, { cache: 'no-store' });
    if (!res.ok) throw new Error("Failed to fetch projects");
    return res.json();
};

export const getProject = async (id: string): Promise<Project & { clips: Clip[] }> => {
    const res = await fetch(`${getBaseUrl()}/api/projects/${id}`, { cache: 'no-store' });
    if (!res.ok) throw new Error("Project not found");
    return res.json();
};

export const createProject = async (youtube_url: string): Promise<{ project_id: string }> => {
    const res = await fetch(`${getBaseUrl()}/api/projects`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ youtube_url })
    });
    if (!res.ok) throw new Error("Failed to create project");
    return res.json();
};

export const deleteProject = async (id: string): Promise<void> => {
    const res = await fetch(`${getBaseUrl()}/api/projects/${id}`, {
        method: 'DELETE'
    });
    if (!res.ok) throw new Error("Failed to delete project");
};

export async function getSettings(): Promise<Settings> {
    const res = await fetch(`${getBaseUrl()}/api/settings`);
    if (!res.ok) throw new Error("Failed to fetch settings");
    return res.json();
}

export async function saveSettings(
    settings: Partial<Settings> & { llm_api_key?: string }
): Promise<void> {
    const res = await fetch(`${getBaseUrl()}/api/settings`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(settings)
    });
    if (!res.ok) throw new Error("Failed to save settings");
}

export async function getCaptionStyles(): Promise<CaptionStyle[]> {
    try {
        const res = await fetch(`${getBaseUrl()}/api/caption-styles`);
        if (res.ok) return res.json();
    } catch {
    }
    return [
        {
            key: "none",
            name: "No Captions",
            animation: "word_by_word",
            preview_colors: { text: "#666666", highlight: null, background: null }
        },
        {
            key: "classic_white",
            name: "Classic White",
            animation: "word_by_word",
            preview_colors: { text: "#FFFFFF", highlight: null, background: null }
        },
        {
            key: "tiktok_style",
            name: "TikTok Style",
            animation: "highlight",
            preview_colors: { text: "#FFFFFF", highlight: "#FFFF00", background: null }
        },
        {
            key: "viral_word",
            name: "Viral Word",
            animation: "one_word",
            preview_colors: { text: "#FFFFFF", highlight: null, background: null }
        }
    ];
}
