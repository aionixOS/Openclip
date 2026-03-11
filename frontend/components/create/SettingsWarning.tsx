"use client";

import Link from "next/link";
import { AlertTriangle, ArrowRight } from "lucide-react";

export function SettingsWarning() {
    return (
        <div className="w-full max-w-2xl mx-auto mb-6 rounded-lg border border-yellow-500/20 bg-yellow-500/10 p-4 animate-in fade-in slide-in-from-top-2">
            <div className="flex items-start md:items-center justify-between gap-4 flex-col md:flex-row">
                <div className="flex items-center gap-3 text-yellow-500">
                    <AlertTriangle className="h-5 w-5 flex-shrink-0" />
                    <div>
                        <p className="font-semibold text-sm">No LLM configured</p>
                        <p className="text-xs text-yellow-500/80">AI clip detection requires an API key.</p>
                    </div>
                </div>
                <Link
                    href="/settings"
                    className="inline-flex h-8 shrink-0 items-center justify-center rounded-sm bg-yellow-500/20 px-4 text-xs font-semibold text-yellow-500 hover:bg-yellow-500/30 transition-colors"
                >
                    Go to Settings
                    <ArrowRight className="ml-1.5 h-3.5 w-3.5" />
                </Link>
            </div>
        </div>
    );
}
