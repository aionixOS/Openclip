import Link from "next/link";
import { Plus, Settings } from "lucide-react";

export function Navbar() {
    return (
        <nav className="sticky top-0 z-50 w-full border-b border-[var(--border)] bg-[var(--background)]/90 backdrop-blur supports-[backdrop-filter]:bg-[var(--background)]/60">
            <div className="container mx-auto flex h-16 items-center px-4 md:px-6">
                <Link href="/" className="flex items-center gap-2 font-semibold text-lg hover:text-[var(--accent)] transition-colors">
                    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="lucide lucide-scissors">
                        <circle cx="6" cy="6" r="3" />
                        <circle cx="6" cy="18" r="3" />
                        <line x1="20" x2="8.12" y1="4" y2="15.88" />
                        <line x1="14.47" x2="20" y1="14.48" y2="20" />
                        <line x1="8.12" x2="12" y1="8.12" y2="12" />
                    </svg>
                    OpenClip
                </Link>
                <div className="flex flex-1 items-center justify-end space-x-4">
                    <Link
                        href="/settings"
                        className="inline-flex h-9 items-center justify-center rounded-sm text-sm font-medium text-gray-400 transition-colors hover:text-[var(--foreground)] focus-visible:outline-none"
                    >
                        <Settings className="mr-2 h-4 w-4" />
                        Settings
                    </Link>
                    <Link
                        href="/create"
                        className="inline-flex h-9 items-center justify-center rounded-sm bg-[var(--accent)] px-4 py-2 text-sm font-medium text-black shadow transition-colors hover:bg-[var(--accent)]/90 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                    >
                        <Plus className="mr-2 h-4 w-4" />
                        New Project
                    </Link>
                </div>
            </div>
        </nav>
    );
}
