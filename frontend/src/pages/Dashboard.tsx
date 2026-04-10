import { useEffect, useMemo, useState } from "react";
import {
  AlertCircle,
  Briefcase,
  Loader2,
  Upload,
  ArrowRight,
} from "lucide-react";
import { Link } from "react-router-dom";
import { api, getReadiness } from "../lib/api";
import type { JobRole } from "../types";

type CandidateCounts = {
  total: number;
  parsed: number;
  processing: number;
};

const StatCard = ({
  title,
  value,
}: {
  title: string;
  value: string | number;
}) => (
  <div className="glass-card rounded-2xl p-6 border border-white/10">
    <p className="text-xs uppercase tracking-wider text-muted-foreground font-semibold">
      {title}
    </p>
    <p className="text-3xl font-bold mt-2">{value}</p>
  </div>
);

export const Dashboard = () => {
  const [roles, setRoles] = useState<JobRole[]>([]);
  const [counts, setCounts] = useState<CandidateCounts>({
    total: 0,
    parsed: 0,
    processing: 0,
  });
  const [readinessOk, setReadinessOk] = useState<boolean>(true);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const run = async () => {
      setLoading(true);
      setError(null);
      try {
        const [rolesRes, countRes] = await Promise.all([
          api.get<JobRole[]>("/job-roles"),
          api.get<CandidateCounts>("/candidates/count"),
        ]);

        setRoles(rolesRes.data);
        setCounts(countRes.data);

        try {
          await getReadiness();
          setReadinessOk(true);
        } catch {
          setReadinessOk(false);
        }
      } catch (err: any) {
        setError(
          err.response?.data?.detail || "Failed to load dashboard data.",
        );
      } finally {
        setLoading(false);
      }
    };

    run();
  }, []);

  const activeRoles = useMemo(() => roles.filter((r) => r.is_active), [roles]);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-24 gap-3">
        <Loader2 className="w-6 h-6 text-primary animate-spin" />
        <p className="text-sm text-muted-foreground">Loading dashboard...</p>
      </div>
    );
  }

  return (
    <div className="space-y-8 animate-in">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-4xl font-bold tracking-tight">
            Smart Talent Engine
          </h1>
          <p className="text-muted-foreground mt-2">
            Operational overview for active roles and parsed candidates.
          </p>
        </div>
        <div className="inline-flex items-center gap-2 px-3 py-2 rounded-full border border-white/10 bg-white/5 text-sm">
          <span
            className={`w-2.5 h-2.5 rounded-full ${readinessOk ? "bg-emerald-400" : "bg-red-400"}`}
          />
          <span>
            {readinessOk
              ? "System operational"
              : "System degraded - some features may not work"}
          </span>
        </div>
      </header>

      {error && (
        <div className="rounded-xl border border-red-500/20 bg-red-500/10 p-4 text-red-300 flex items-center gap-2 text-sm">
          <AlertCircle className="w-4 h-4" />
          <span>{error}</span>
        </div>
      )}

      <section className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <StatCard title="Active Roles" value={activeRoles.length} />
        <StatCard title="Parsed Candidates" value={counts.parsed} />
        <StatCard title="In Pipeline" value={counts.processing} />
      </section>

      <section className="glass-card rounded-3xl p-6 border border-white/10">
        <div className="flex items-center justify-between mb-5">
          <h2 className="text-xl font-bold">Job Roles</h2>
          <Link to="/jobs" className="text-sm text-primary hover:underline">
            View all roles
          </Link>
        </div>

        {activeRoles.length === 0 ? (
          <div className="py-10 text-center">
            <p className="text-sm text-muted-foreground">
              No active roles. Create one to get started.
            </p>
            <Link
              to="/jobs"
              className="text-primary hover:underline text-sm mt-2 inline-block"
            >
              Go to Job Roles
            </Link>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-muted-foreground border-b border-white/10">
                  <th className="py-3 pr-3">Title</th>
                  <th className="py-3 pr-3">Parsed</th>
                  <th className="py-3">Action</th>
                </tr>
              </thead>
              <tbody>
                {activeRoles.map((role) => (
                  <tr
                    key={role.id}
                    className="border-b border-white/5 last:border-0"
                  >
                    <td className="py-4 pr-3">
                      <div className="flex items-center gap-2">
                        <Briefcase className="w-4 h-4 text-muted-foreground" />
                        <span>{role.title}</span>
                      </div>
                    </td>
                    <td className="py-4 pr-3">
                      <span>{role.resume_count}</span>
                    </td>
                    <td className="py-4">
                      <div className="flex items-center gap-2">
                        <Link
                          to={`/jobs/${role.id}/upload`}
                          className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-md border border-white/10 bg-white/5 hover:bg-white/10"
                        >
                          <Upload className="w-3 h-3" />
                          Upload
                        </Link>
                        <Link
                          to={`/jobs/${role.id}/rank`}
                          className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-md border border-primary/30 bg-primary/10 text-primary hover:bg-primary hover:text-primary-foreground"
                        >
                          Rank
                          <ArrowRight className="w-3 h-3" />
                        </Link>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
};
