"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Plus, Scissors } from "lucide-react";
import { getProjects, deleteProject } from "@/lib/api";
import { Project } from "@/lib/types";
import { ProjectCard } from "@/components/dashboard/ProjectCard";
import { EmptyState } from "@/components/dashboard/EmptyState";
import { ProjectCardSkeleton } from "@/components/dashboard/ProjectCardSkeleton";

export default function Dashboard() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function loadProjects() {
      try {
        const data = await getProjects();
        setProjects(data);
      } catch (err) {
        console.error("Failed to load projects", err);
        setError(err instanceof Error ? err.message : "Failed to load projects");
      } finally {
        setLoading(false);
      }
    }
    loadProjects();
  }, []);

  const loadProjectsRetry = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getProjects();
      setProjects(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load projects");
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (id: string) => {
    try {
      await deleteProject(id);
      setProjects((prev) => prev.filter((p) => p.id !== id));
    } catch (err) {
      console.error("Failed to delete project", err);
    }
  };

  return (
    <div className="container mx-auto px-4 py-8 md:px-6 md:py-12 max-w-6xl">
      {/* Hero Section */}
      <div className="mb-10 flex flex-col items-start justify-between gap-4 md:flex-row md:items-center">
        <div>
          <h1 className="text-3xl font-bold tracking-tight text-[var(--foreground)] sm:text-4xl flex items-center gap-3">
            <Scissors className="h-8 w-8 text-[var(--accent)]" />
            Your Projects
          </h1>
          <p className="mt-2 text-lg text-gray-400">
            Turn any YouTube video into clips automatically.
          </p>
        </div>
        <Link
          href="/create"
          className="inline-flex h-11 items-center justify-center rounded-sm bg-[var(--accent)] px-6 py-2 text-sm font-semibold text-black shadow transition-all hover:bg-[var(--accent)]/90 hover:scale-105 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <Plus className="mr-2 h-5 w-5" />
          Create New Project
        </Link>
      </div>

      {/* Main Content */}
      {loading ? (
        <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3">
          <ProjectCardSkeleton count={3} />
        </div>
      ) : error ? (
        <div className="text-center bg-[var(--surface)] border border-[var(--error)]/50 rounded-lg p-12 mt-8">
          <h3 className="text-lg font-semibold text-[var(--error)] mb-2">Failed to load projects</h3>
          <p className="text-gray-400 mb-6">{error}</p>
          <button
            onClick={loadProjectsRetry}
            className="bg-[var(--surface)] border border-[var(--border)] hover:bg-gray-800 px-4 py-2 rounded-sm text-sm"
          >
            Retry
          </button>
        </div>
      ) : projects.length === 0 ? (
        <EmptyState />
      ) : (
        <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3">
          {projects.map((project) => (
            <ProjectCard key={project.id} project={project} onDelete={handleDelete} />
          ))}
        </div>
      )}
    </div>
  );
}
