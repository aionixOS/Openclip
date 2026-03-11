export interface Project {
    id: string;
    youtube_url: string;
    title: string;
    status: 'pending' | 'downloading' | 'processing' | 'done' | 'error';
    created_at: string;
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
    animation: 'word_by_word' | 'highlight';
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
