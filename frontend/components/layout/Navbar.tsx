"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useState, useEffect } from "react";

export function Navbar() {
    const pathname = usePathname();
    const router = useRouter();
    const searchParams = useSearchParams();
    const [searchValue, setSearchValue] = useState(searchParams.get("q") || "");

    useEffect(() => {
        setSearchValue(searchParams.get("q") || "");
    }, [searchParams]);

    const handleSearch = (e: React.ChangeEvent<HTMLInputElement>) => {
        const val = e.target.value;
        setSearchValue(val);
        const params = new URLSearchParams();
        if (val.trim()) params.set("q", val.trim());
        router.push(`/?${params.toString()}`);
    };

    return (
        <header className="sticky top-0 z-50 w-full glass-dark px-6 lg:px-20 py-4">
            <div className="mx-auto flex max-w-7xl items-center justify-between">
                <div className="flex items-center gap-10">
                    <Link href="/" className="flex items-center gap-3">
                        <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary glow-primary">
                            <svg className="h-5 w-5 text-white" viewBox="0 0 24 24" fill="currentColor">
                                <path d="M2 6a2 2 0 012-2h16a2 2 0 012 2v.5a.5.5 0 01-1 0V6a1 1 0 00-1-1H4a1 1 0 00-1 1v12a1 1 0 001 1h16a1 1 0 001-1v-.5a.5.5 0 011 0V18a2 2 0 01-2 2H4a2 2 0 01-2-2V6z"/>
                                <path d="M15.5 8a.5.5 0 01.5.5v7a.5.5 0 01-.5.5h-7a.5.5 0 010-1H15V8.5a.5.5 0 01.5-.5z"/>
                                <path fillRule="evenodd" d="M9.854 8.146a.5.5 0 010 .708L7.707 11H14.5a.5.5 0 010 1H7.707l2.147 2.146a.5.5 0 01-.708.708l-3-3a.5.5 0 010-.708l3-3a.5.5 0 01.708 0z" clipRule="evenodd"/>
                            </svg>
                        </div>
                        <span className="text-xl font-bold tracking-tight text-white">OpenClip</span>
                    </Link>
                    <nav className="hidden md:flex items-center gap-6">
                        <Link href="/" className={`text-sm font-medium transition-colors ${pathname === "/" ? "text-white" : "text-slate-400 hover:text-white"}`}>
                            Projects
                        </Link>
                        <Link href="/create" className={`text-sm font-medium transition-colors ${pathname === "/create" ? "text-white" : "text-slate-400 hover:text-white"}`}>
                            Create
                        </Link>
                        <Link href="/settings" className={`text-sm font-medium transition-colors ${pathname === "/settings" ? "text-white" : "text-slate-400 hover:text-white"}`}>
                            Settings
                        </Link>
                    </nav>
                </div>

                <div className="flex flex-1 items-center justify-end gap-3">
                    <div className="relative hidden lg:block w-full max-w-xs">
                        <svg className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"/></svg>
                        <input
                            className="w-full rounded-full bg-white/5 border border-white/10 py-2 pl-10 pr-4 text-sm text-white placeholder-slate-500 focus:border-primary focus:outline-none transition-all"
                            placeholder="Search projects..."
                            type="text"
                            value={searchValue}
                            onChange={handleSearch}
                        />
                    </div>
                    <Link href="/settings" className="flex h-9 w-9 items-center justify-center rounded-full glass glass-hover text-slate-300 transition-all">
                        <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"/><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/></svg>
                    </Link>
                </div>
            </div>
        </header>
    );
}
