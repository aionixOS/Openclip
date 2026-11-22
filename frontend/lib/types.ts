export interface Project {
    id: string;
    youtube_url: string;
    title: string;
    status:
        | 'pending'
        | 'downloading'
        | 'transcribing'
        | 'analyzing'
        | 'processing'
        | 'done'
        | 'error';
    created_at: string;
    /** Why the last run failed, or which clips were skipped. */
    error_message?: string | null;
    clip_count?: number;
}

export interface Clip {
    id: string
    project_id: string
    file_path: string
    start_time: number
    end_time: number
    duration: number
    reframed: boolean
    captioned: boolean
    title?: string
    reason?: string
    viral_score?: number
    face_count?: number
    hashtags?: string[]
    tags?: string[]
}

export interface ProgressUpdate {
    stage: string;
    percent: number;
    message: string;
}

export interface Settings {
    llm_provider: 'openai' | 'anthropic' | 'gemini' | 'ollama';
    llm_model: string;
    whisper_model: 'base' | 'small' | 'medium';
    has_api_key: boolean;
    caption_style: string;
}

export interface CaptionStyle {
    key: string;
    name: string;
    animation: 'word_by_word' | 'highlight' | 'one_word';
    preview_colors: {
        text: string;
        highlight: string | null;
        background: string | null;
    };
}

export interface ClipSuggestion {
    start: number;
    end: number;
    title: string;
    reason: string;
}

export interface SystemTool {
    id: 'ffmpeg' | 'yt_dlp' | 'python_packages';
    name: string;
    description: string;
    ok: boolean;
    can_install: boolean;
    manual: string;
    missing?: string[];
}

export interface InstallStep {
    id: SystemTool['id'];
    name: string;
    state: 'pending' | 'running' | 'done' | 'error';
    progress: number;
    detail: string;
}

export interface InstallJob {
    state: 'idle' | 'running' | 'done' | 'error';
    percent: number;
    message: string;
    steps: InstallStep[];
    error: string | null;
    log: string[];
}

export interface SystemHealth {
    ready: boolean;
    platform: 'windows' | 'macos' | 'linux';
    tools: SystemTool[];
    install: InstallJob;
}
