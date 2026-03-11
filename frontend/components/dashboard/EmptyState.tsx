import Link from "next/link";
import { Plus, Video } from "lucide-react";

export function EmptyState() {
    return (
        <div className="flex flex-col items-center justify-center rounded-lg border border-dashed border-[var(--border)] bg-[var(--surface)] p-12 text-center mt-8">
            <div className="flex h-20 w-20 items-center justify-center rounded-full bg-[var(--background)] mb-4 shadow-sm border border-[var(--border)]">
                <Video className="h-10 w-10 text-gray-400" />
            </div>
            <h3 className="text-xl font-semibold mb-2 text-[var(--foreground)]">No projects yet</h3>
            <p className="text-sm text-gray-400 mb-6 max-w-sm">
                Start by creating your first project. Paste a YouTube URL to get started with the clipping process.
            </p>
            <Link
                href="/create"
                className="inline-flex h-10 items-center justify-center rounded-sm bg-[var(--accent)] px-4 py-2 text-sm font-medium text-black shadow transition-colors hover:bg-[var(--accent)]/90 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
            >
                <Plus className="mr-2 h-4 w-4" />
                Create New
            </Link>
        </div>
    );
}
