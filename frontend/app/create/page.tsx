"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { UrlInput } from "@/components/create/UrlInput";
import { ProgressBar } from "@/components/create/ProgressBar";
import { ClipGrid } from "@/components/create/ClipGrid";
import { SettingsWarning } from "@/components/create/SettingsWarning";
import { createProject, getProject, getSettings, saveSettings, BASE_URL } from "@/lib/api";
import { Clip, Settings } from "@/lib/types";
import { useProjectProgress } from "@/lib/websocket";
import { ArrowRight, Terminal } from "lucide-react";
import { useRef } from "react";

export default function CreateProjectPage() {
    const router = useRouter();
    const [isProcessing, setIsProcessing] = useState(false);
    const [generatedClips, setGeneratedClips] = useState<Clip[]>([]);
    const [projectId, setProjectId] = useState<string | null>(null);
    const [apiError, setApiError] = useState<string | null>(null);
    const [hasApiKey, setHasApiKey] = useState<boolean | null>(null);
    const [provider, setProvider] = useState<Settings['llm_provider']>('openai');
    const [model, setModel] = useState("gpt-4o");

    const { stage, percent, message, logs } = useProjectProgress(projectId);

    // Auto-scroll logs to bottom
    const logsEndRef = useRef<HTMLDivElement>(null);
    useEffect(() => {
        if (logsEndRef.current) {
            logsEndRef.current.scrollIntoView({ behavior: "smooth" });
        }
    }, [logs]);

    useEffect(() => {
        getSettings().then(s => {
            setHasApiKey(s.has_api_key);
            setProvider(s.llm_provider);
            setModel(s.llm_model);
        }).catch(console.error);
    }, []);

    useEffect(() => {
        if (stage === "done" && projectId) {
            // Fetch clips when websocket says done
            getProject(projectId).then(data => {
                setGeneratedClips(data.clips || []);
                setIsProcessing(false);
            }).catch(err => {
                console.error("Failed to fetch clips:", err);
                setApiError("Failed to load generated clips.");
                setIsProcessing(false);
            });
        } else if (stage === "error") {
            setIsProcessing(false);
        }
    }, [stage, projectId]);

    const handleProviderChange = (newProvider: Settings['llm_provider']) => {
        setProvider(newProvider);
        if (newProvider === 'openai') setModel('gpt-4o');
        if (newProvider === 'anthropic') setModel('claude-3-5-sonnet-20241022');
        if (newProvider === 'gemini') setModel('gemini-1.5-pro');
        if (newProvider === 'ollama') setModel('llama3');
    };

    const handleGenerate = async (url: string) => {
        setIsProcessing(true);
        setGeneratedClips([]);
        setApiError(null);
        setProjectId(null);

        try {
            await saveSettings({ llm_provider: provider, llm_model: model });
            const { project_id } = await createProject(url);
            setProjectId(project_id); // This will trigger the websocket connection via useProjectProgress
        } catch (err) {
            console.error("Error creating project:", err);
            setApiError("Something went wrong. Try again.");
            setIsProcessing(false);
        }
    };

    return (
        <div className="container flex flex-col items-center justify-center min-h-[calc(100vh-4rem)] py-12 px-4 mx-auto max-w-5xl">
            <div className="text-center mb-12 animate-in fade-in slide-in-from-bottom-4 duration-500">
                <h1 className="text-4xl md:text-5xl font-bold tracking-tight mb-4 text-[var(--foreground)]">
                    Create New Project
                </h1>
                <p className="text-lg text-gray-400 max-w-2xl mx-auto">
                    Paste any YouTube URL below to automatically download, analyze, and generate short-form clips tailored for social media.
                </p>
            </div>

            <div className="w-full flex-1 flex flex-col items-center">
                {apiError && (
                    <div className="mb-4 text-center">
                        <p className="text-[var(--error)] font-medium mb-2">{apiError}</p>
                    </div>
                )}

                {hasApiKey === false && <SettingsWarning />}

                <div className="w-full max-w-2xl bg-[var(--surface)] border border-[var(--border)] rounded-lg p-6 mb-8 shadow-sm">
                    <UrlInput onSubmit={handleGenerate} isLoading={isProcessing} />

                    <div className="mt-4 pt-4 border-t border-[var(--border)] flex flex-col md:flex-row gap-4">
                        <div className="flex-1">
                            <label className="block text-xs font-medium text-gray-400 mb-1.5">
                                AI Provider
                            </label>
                            <select
                                value={provider}
                                onChange={(e) => handleProviderChange(e.target.value as Settings['llm_provider'])}
                                disabled={isProcessing}
                                className="w-full h-9 px-3 rounded-md border border-[var(--border)] bg-[var(--background)] text-sm text-[var(--foreground)] focus:outline-none focus:ring-1 focus:ring-[var(--accent)] transition-all disabled:opacity-50"
                            >
                                <option value="openai">OpenAI</option>
                                <option value="anthropic">Anthropic</option>
                                <option value="gemini">Google Gemini</option>
                                <option value="ollama">Ollama (Local)</option>
                            </select>
                        </div>
                        <div className="flex-1">
                            <label className="block text-xs font-medium text-gray-400 mb-1.5">
                                Model Engine
                            </label>
                            <input
                                type="text"
                                value={model}
                                onChange={(e) => setModel(e.target.value)}
                                disabled={isProcessing}
                                className="w-full h-9 px-3 rounded-md border border-[var(--border)] bg-[var(--background)] text-sm text-[var(--foreground)] focus:outline-none focus:ring-1 focus:ring-[var(--accent)] transition-all disabled:opacity-50"
                            />
                        </div>
                    </div>
                </div>

                {projectId && (
                    <div className="w-full flex flex-col items-center">
                        <div className="w-full">
                            <ProgressBar stage={stage} percent={percent} visible={true} />
                        </div>

                        {/* Terminal Logs View */}
                        <div className="w-full max-w-2xl mt-6 rounded-lg border border-[var(--border)] bg-[#0d0d0d] overflow-hidden shadow-sm">
                            <div className="flex items-center px-4 py-2 border-b border-[var(--border)] bg-[#151515]">
                                <Terminal className="h-4 w-4 text-gray-500 mr-2" />
                                <span className="text-xs font-mono text-gray-400">Pipeline Output</span>
                            </div>
                            <div className="p-4 h-64 overflow-y-auto font-mono text-xs flex flex-col gap-1">
                                {logs.length === 0 ? (
                                    <span className="text-gray-500 italic">Connecting to server pipeline...</span>
                                ) : (
                                    logs.map((log, i) => {
                                        const isErrorLog = stage === "error" && i === logs.length - 1;
                                        return (
                                            <div key={i} className={isErrorLog ? "text-red-500 font-medium" : "text-gray-300"}>
                                                <span className={isErrorLog ? "text-red-500 mr-2" : "text-green-500 mr-2"}>
                                                    {isErrorLog ? "✖" : "›"}
                                                </span>
                                                {log}
                                            </div>
                                        );
                                    })
                                )}
                                <div ref={logsEndRef} />
                            </div>
                        </div>
                    </div>
                )}

                {generatedClips.length > 0 && stage === "done" && (
                    <div className="w-full flex flex-col items-center mt-12 animate-in fade-in slide-in-from-bottom-8">
                        <ClipGrid clips={generatedClips} baseUrl={BASE_URL} />
                        <button
                            onClick={() => router.push(`/project/${projectId}`)}
                            className="mt-8 inline-flex h-11 items-center justify-center rounded-sm bg-[var(--surface)] border border-[var(--border)] px-8 py-2 font-semibold text-[var(--foreground)] hover:bg-gray-800 transition-colors"
                        >
                            View Full Project
                            <ArrowRight className="ml-2 h-5 w-5" />
                        </button>
                    </div>
                )}
            </div>
        </div>
    );
}
