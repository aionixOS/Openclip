import { Project, Clip, Settings, CaptionStyle } from './types';

export const getProjects = async (): Promise<Project[]> => {
    const res = await fetch(`${BASE_URL}/api/projects`, { cache: 'no-store' });
    if (!res.ok) throw new Error("Failed to fetch projects");
    return res.json();
};

export const getProject = async (id: string): Promise<Project & { clips: Clip[] }> => {
    const res = await fetch(`${BASE_URL}/api/projects/${id}`, { cache: 'no-store' });
    if (!res.ok) throw new Error("Project not found");
    return res.json();
};

export const createProject = async (youtube_url: string): Promise<{ project_id: string }> => {
    const res = await fetch(`${BASE_URL}/api/projects`, {
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
    const res = await fetch(`${BASE_URL}/api/projects/${id}`, {
        method: 'DELETE'
    });
    if (!res.ok) throw new Error("Failed to delete project");
};

export async function getSettings(): Promise<Settings> {
    const res = await fetch(`${BASE_URL}/api/settings`);
    if (!res.ok) throw new Error("Failed to fetch settings");
    return res.json();
}

export async function saveSettings(
    settings: Partial<Settings> & { llm_api_key?: string }
): Promise<void> {
    const res = await fetch(`${BASE_URL}/api/settings`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(settings)
    });
    if (!res.ok) throw new Error("Failed to save settings");
}

export const BASE_URL = "http://localhost:8000";

// TODO: connect to backend
export async function getCaptionStyles(): Promise<CaptionStyle[]> {
    return Promise.resolve([
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
        }
        // Integration agent will replace with real API call
    ]);
}
