"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { ArrowLeft, CheckCircle2, AlertCircle, Loader2 } from "lucide-react";
import { getSettings, saveSettings, getCaptionStyles } from "@/lib/api";
import { Settings, CaptionStyle } from "@/lib/types";
import { CaptionStyleCard } from "@/components/settings/CaptionStyleCard";

export default function SettingsPage() {
    const router = useRouter();

    // UI States
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);
    const [savedStatus, setSavedStatus] = useState<string | null>(null);
    const [error, setError] = useState<string | null>(null);

    // Form data
    const [provider, setProvider] = useState<Settings['llm_provider']>('openai');
    const [model, setModel] = useState("gpt-4o");
    const [whisperModel, setWhisperModel] = useState<Settings['whisper_model']>('base');
    const [captionStyle, setCaptionStyle] = useState<string>('none');
    const [captionStylesList, setCaptionStylesList] = useState<CaptionStyle[]>([]);
    const [apiKey, setApiKey] = useState("");
    const [hasApiKey, setHasApiKey] = useState(false);

    // For handling the "Change" button state logic
    const [editingKey, setEditingKey] = useState(false);

    useEffect(() => {
        Promise.all([getSettings(), getCaptionStyles()]).then(([data, styles]) => {
            setProvider(data.llm_provider);
            setModel(data.llm_model);
            setWhisperModel(data.whisper_model);
            setCaptionStyle(data.caption_style || 'none');
            setHasApiKey(data.has_api_key);
            setCaptionStylesList(styles);
            setLoading(false);
        }).catch(err => {
            console.error("Failed to load settings:", err);
            setError("Failed to load settings.");
            setLoading(false);
        });
    }, []);

    const handleSave = async (e: React.FormEvent) => {
        e.preventDefault();
        setSaving(true);
        setError(null);
        setSavedStatus(null);

        try {
            const payload: Partial<Settings> & { llm_api_key?: string } = {
                llm_provider: provider,
                llm_model: model,
                whisper_model: whisperModel,
                caption_style: captionStyle,
            };

            // Only send API key if they are actively editing/providing a new one
            if (editingKey || (!hasApiKey && apiKey)) {
                payload.llm_api_key = apiKey;
            }

            await saveSettings(payload);

            setSavedStatus("Settings saved");
            setHasApiKey(true);
            setEditingKey(false);
            setApiKey("");

            setTimeout(() => setSavedStatus(null), 2000);
        } catch (err) {
            console.error("Save failed:", err);
            setError("Failed to save settings. Please try again.");
        } finally {
            setSaving(false);
        }
    };

    const handleProviderChange = (newProvider: Settings['llm_provider']) => {
        setProvider(newProvider);
        // Reset defaults
        if (newProvider === 'openai') setModel('gpt-4o');
        if (newProvider === 'anthropic') setModel('claude-3-5-sonnet-20241022');
        if (newProvider === 'gemini') setModel('gemini-1.5-pro');
        if (newProvider === 'ollama') setModel('llama3');
    };

    if (loading) {
        return (
            <div className="container mx-auto px-4 py-12 flex flex-col items-center justify-center min-h-[50vh]">
                <Loader2 className="h-8 w-8 animate-spin text-[var(--accent)] mb-4" />
                <p className="text-gray-400">Loading settings...</p>
            </div>
        );
    }

    return (
        <div className="container mx-auto px-4 py-8 md:px-6 md:py-12 max-w-3xl animate-in fade-in duration-500">
            <button
                onClick={() => router.push('/')}
                className="inline-flex items-center text-sm text-gray-400 hover:text-[var(--foreground)] transition-colors mb-8"
            >
                <ArrowLeft className="mr-2 h-4 w-4" />
                Back to Dashboard
            </button>

            <h1 className="text-3xl font-bold tracking-tight text-[var(--foreground)] mb-8">
                Settings
            </h1>

            <form onSubmit={handleSave} className="space-y-8">

                {/* SECTION 1 - LLM Provider */}
                <div className="bg-[var(--surface)] border border-[var(--border)] rounded-lg p-6">
                    <h2 className="text-xl font-semibold mb-6 flex items-center text-[var(--foreground)]">
                        AI Provider
                    </h2>

                    <div className="space-y-6">
                        <div>
                            <label className="block text-sm font-medium text-gray-300 mb-2">
                                Select Provider
                            </label>
                            <select
                                value={provider}
                                onChange={(e) => handleProviderChange(e.target.value as Settings['llm_provider'])}
                                className="w-full h-10 px-3 rounded-md border border-[var(--border)] bg-[var(--background)] text-[var(--foreground)] focus:outline-none focus:ring-2 focus:ring-[var(--accent)] transition-all"
                            >
                                <option value="openai">OpenAI</option>
                                <option value="anthropic">Anthropic</option>
                                <option value="gemini">Google Gemini</option>
                                <option value="ollama">Ollama (Local)</option>
                            </select>
                        </div>

                        {provider !== 'ollama' && (
                            <div>
                                <label className="block text-sm font-medium text-gray-300 mb-2">
                                    API Key
                                </label>

                                {hasApiKey && !editingKey ? (
                                    <div className="flex items-center justify-between p-3 rounded-md border text-sm border-[var(--success)]/30 bg-[var(--success)]/10 text-[var(--success)]">
                                        <div className="flex items-center gap-2">
                                            <CheckCircle2 className="h-4 w-4" />
                                            <span>API key saved ✓</span>
                                        </div>
                                        <button
                                            type="button"
                                            onClick={() => setEditingKey(true)}
                                            className="font-semibold hover:underline"
                                        >
                                            Change
                                        </button>
                                    </div>
                                ) : (
                                    <div className="space-y-2">
                                        <input
                                            type="password"
                                            value={apiKey}
                                            onChange={(e) => setApiKey(e.target.value)}
                                            placeholder={
                                                provider === 'openai' ? "sk-..." :
                                                    provider === 'anthropic' ? "sk-ant-..." :
                                                        "AIza..."
                                            }
                                            className="w-full h-10 px-3 rounded-md border border-[var(--border)] bg-[var(--background)] text-[var(--foreground)] focus:outline-none focus:ring-2 focus:ring-[var(--accent)] transition-all"
                                            required={!hasApiKey || editingKey}
                                        />
                                        <div className="flex justify-end">
                                            <a
                                                href={
                                                    provider === 'openai' ? "https://platform.openai.com" :
                                                        provider === 'anthropic' ? "https://console.anthropic.com" :
                                                            "https://aistudio.google.com"
                                                }
                                                target="_blank"
                                                rel="noreferrer"
                                                className="text-xs text-[var(--accent)] hover:underline"
                                            >
                                                Get API key &rarr;
                                            </a>
                                        </div>
                                        {hasApiKey && editingKey && (
                                            <button
                                                type="button"
                                                onClick={() => { setEditingKey(false); setApiKey(""); }}
                                                className="text-xs text-gray-400 hover:text-white"
                                            >
                                                Cancel change
                                            </button>
                                        )}
                                    </div>
                                )}
                            </div>
                        )}

                        <div>
                            <label className="block text-sm font-medium text-gray-300 mb-2">
                                Model Version
                            </label>
                            <input
                                type="text"
                                value={model}
                                onChange={(e) => setModel(e.target.value)}
                                className="w-full h-10 px-3 rounded-md border border-[var(--border)] bg-[var(--background)] text-[var(--foreground)] focus:outline-none focus:ring-2 focus:ring-[var(--accent)] transition-all"
                                required
                            />
                            {provider === 'ollama' && (
                                <p className="mt-2 text-xs text-blue-400 bg-blue-500/10 p-2 rounded border border-blue-500/20">
                                    Make sure Ollama is running on localhost:11434
                                </p>
                            )}
                        </div>
                    </div>
                </div>

                {/* SECTION 2 - Transcription */}
                <div className="bg-[var(--surface)] border border-[var(--border)] rounded-lg p-6">
                    <h2 className="text-xl font-semibold mb-6 flex items-center text-[var(--foreground)]">
                        Transcription
                    </h2>

                    <div>
                        <label className="block text-sm font-medium text-gray-300 mb-2">
                            Whisper Model
                        </label>
                        <select
                            value={whisperModel}
                            onChange={(e) => setWhisperModel(e.target.value as Settings['whisper_model'])}
                            className="w-full h-10 px-3 rounded-md border border-[var(--border)] bg-[var(--background)] text-[var(--foreground)] focus:outline-none focus:ring-2 focus:ring-[var(--accent)] transition-all"
                        >
                            <option value="base">Base (Fast, less accurate)</option>
                            <option value="small">Small (Balanced)</option>
                            <option value="medium">Medium (Slow, most accurate)</option>
                        </select>
                        <p className="mt-2 text-xs text-gray-500">
                            Higher accuracy variants will take substantially longer to compile the transcriptions on CPU.
                        </p>
                    </div>
                </div>

                {/* SECTION 3 - Captions */}
                <div className="bg-[var(--surface)] border border-[var(--border)] rounded-lg p-6">
                    <h2 className="text-xl font-semibold mb-6 flex items-center text-[var(--foreground)]">
                        Caption Style
                    </h2>

                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                        {captionStylesList.map((style) => (
                            <CaptionStyleCard
                                key={style.key}
                                styleKey={style.key}
                                name={style.name}
                                animation={style.animation}
                                previewColors={style.preview_colors}
                                selected={captionStyle === style.key}
                                onSelect={setCaptionStyle}
                            />
                        ))}
                    </div>
                </div>

                {error && (
                    <div className="p-4 rounded-md bg-[var(--error)]/10 border border-[var(--error)]/20 flex gap-3 text-[var(--error)] mt-4">
                        <AlertCircle className="h-5 w-5 shrink-0" />
                        <p className="text-sm font-medium">{error}</p>
                    </div>
                )}

                <div className="flex items-center gap-4 pt-4">
                    <button
                        type="submit"
                        disabled={saving}
                        className="h-10 px-6 rounded-sm bg-[var(--accent)] text-black font-semibold disabled:opacity-50 hover:bg-[var(--accent)]/90 transition-colors focus-visible:outline-none"
                    >
                        {saving ? "Saving..." : "Save Settings"}
                    </button>

                    {savedStatus && (
                        <span className="text-sm font-medium text-[var(--success)] flex items-center gap-1 animate-in fade-in slide-in-from-left-2">
                            <CheckCircle2 className="h-4 w-4" />
                            {savedStatus}
                        </span>
                    )}
                </div>
            </form>
        </div>
    );
}
