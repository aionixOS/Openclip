"use client";

import { useState } from "react";
import { ClipboardPaste, Link as LinkIcon } from "lucide-react";

interface UrlInputProps {
    onSubmit: (url: string) => void;
    isLoading: boolean;
}

export function UrlInput({ onSubmit, isLoading }: UrlInputProps) {
    const [url, setUrl] = useState("");

    const isValidYoutubeUrl = (url: string) => {
        const pattern = /^(https?:\/\/)?(www\.youtube\.com|youtu\.?be)\/.+$/;
        return pattern.test(url);
    };

    const handlePaste = async () => {
        try {
            const text = await navigator.clipboard.readText();
            setUrl(text);
        } catch (err) {
            console.error("Failed to read clipboard text: ", err);
        }
    };

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault();
        if (isValidYoutubeUrl(url) && !isLoading) {
            onSubmit(url);
        }
    };

    const isValid = isValidYoutubeUrl(url);

    return (
        <div className="w-full max-w-2xl mx-auto">
            <form onSubmit={handleSubmit} className="relative">
                <div className="relative flex items-center">
                    <LinkIcon className="absolute left-4 h-5 w-5 text-gray-400" />
                    <input
                        type="text"
                        value={url}
                        onChange={(e) => setUrl(e.target.value)}
                        placeholder="Paste YouTube URL here..."
                        className="w-full h-14 pl-12 pr-32 rounded-lg border border-[var(--border)] bg-[var(--surface)] text-[var(--foreground)] placeholder:text-gray-500 focus:outline-none focus:ring-2 focus:ring-[var(--accent)] focus:border-transparent transition-all"
                        disabled={isLoading}
                    />
                    <div className="absolute right-2 flex items-center gap-2">
                        {!url && (
                            <button
                                type="button"
                                onClick={handlePaste}
                                className="p-2 text-gray-400 hover:text-[var(--foreground)] transition-colors rounded-sm hover:bg-gray-800"
                                title="Paste from clipboard"
                                disabled={isLoading}
                            >
                                <ClipboardPaste className="h-5 w-5" />
                            </button>
                        )}
                        <button
                            type="submit"
                            disabled={!isValid || isLoading}
                            className="h-10 px-4 rounded-sm bg-[var(--accent)] text-black font-medium disabled:opacity-50 disabled:cursor-not-allowed hover:bg-[var(--accent)]/90 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-[var(--accent)] focus-visible:ring-offset-[var(--background)]"
                        >
                            {isLoading ? "Processing..." : "Generate Clips"}
                        </button>
                    </div>
                </div>
                {url && !isValid && (
                    <p className="absolute -bottom-6 left-0 text-sm text-[var(--error)]">
                        Please enter a valid YouTube URL
                    </p>
                )}
            </form>
        </div>
    );
}
