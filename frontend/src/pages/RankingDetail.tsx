import { useState, useEffect, useCallback, useRef } from "react";
import {
  ArrowLeft,
  Upload,
  Settings2,
  ChevronDown,
  ChevronUp,
  BrainCircuit,
  FileText,
  Loader2,
  AlertCircle,
  FolderOpen,
  X,
  TriangleAlert,
  RefreshCw,
} from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { Link, useParams } from "react-router-dom";
import { api, getResumeFileUrl } from "../lib/api";
import type {
  JobRole,
  JobDescription,
  CandidateRankingResult,
  JobDescriptionRankingResponse,
  ScoringConfig,
  ScoringConfigUpdate,
} from "../types";

type ProfilePanelProps = {
  candidate: CandidateRankingResult | null;
  onClose: () => void;
};

const ProfilePanel = ({ candidate, onClose }: ProfilePanelProps) => {
  if (!candidate) return null;

  const profile = candidate.candidate.profile_json || {};
  const experiences = Array.isArray(profile.experience)
    ? profile.experience
    : [];
  const projects = Array.isArray(profile.projects) ? profile.projects : [];
  const education = Array.isArray(profile.education) ? profile.education : [];
  const certifications = Array.isArray(profile.certifications)
    ? profile.certifications
    : [];
  const skills = Array.isArray(profile.skills)
    ? profile.skills
    : candidate.candidate.skills;
  const linkedInUrl =
    profile.linkedin_url ||
    profile.linkedin ||
    candidate.candidate.profile_json?.linkedin_url;
  const githubUrl =
    profile.github_url ||
    profile.github ||
    candidate.candidate.profile_json?.github_url;
  const portfolioUrl =
    profile.portfolio_url ||
    profile.website ||
    candidate.candidate.profile_json?.portfolio_url;

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className="fixed inset-0 bg-black/50 z-50"
        onClick={onClose}
      >
        <motion.div
          initial={{ x: 440 }}
          animate={{ x: 0 }}
          exit={{ x: 440 }}
          transition={{ type: "spring", stiffness: 260, damping: 28 }}
          className="absolute right-0 top-0 h-full w-full max-w-xl bg-slate-950 border-l border-border overflow-y-auto"
          onClick={(e) => e.stopPropagation()}
        >
          <div className="p-6 border-b border-white/10 flex items-start justify-between">
            <div>
              <h2 className="text-xl font-bold">
                {candidate.candidate.full_name}
              </h2>
              <p className="text-sm text-muted-foreground">
                {candidate.candidate.email || "Email not available"}
              </p>
              <p className="text-sm text-muted-foreground mt-1">
                {candidate.candidate.total_exp_years} years experience
              </p>
            </div>
            <button
              className="p-2 rounded-lg hover:bg-white/10"
              onClick={onClose}
            >
              <X className="w-5 h-5" />
            </button>
          </div>

          <div className="p-6 space-y-6">
            <section>
              <h3 className="text-sm font-bold uppercase text-muted-foreground tracking-wide mb-2">
                Contact
              </h3>
              <div className="space-y-1 text-sm">
                <p>Phone: {profile.phone || "N/A"}</p>
                <p>LinkedIn: {linkedInUrl ? (
                  <a href={linkedInUrl} target="_blank" rel="noopener noreferrer" className="text-primary hover:underline">{linkedInUrl}</a>
                ) : "N/A"}</p>
                <p>GitHub: {githubUrl ? (
                  <a href={githubUrl} target="_blank" rel="noopener noreferrer" className="text-primary hover:underline">{githubUrl}</a>
                ) : "N/A"}</p>
                <p>Portfolio: {portfolioUrl ? (
                  <a href={portfolioUrl} target="_blank" rel="noopener noreferrer" className="text-primary hover:underline">{portfolioUrl}</a>
                ) : "N/A"}</p>
              </div>
            </section>

            <section>
              <h3 className="text-sm font-bold uppercase text-muted-foreground tracking-wide mb-2">
                Skills
              </h3>
              <div className="flex flex-wrap gap-2">
                {skills.length > 0 ? (
                  skills.map((skill: string) => (
                    <span
                      key={skill}
                      className="text-xs px-2 py-1 rounded-md bg-white/5 border border-white/10"
                    >
                      {skill}
                    </span>
                  ))
                ) : (
                  <p className="text-sm text-muted-foreground">
                    No skills listed
                  </p>
                )}
              </div>
            </section>

            <section>
              <h3 className="text-sm font-bold uppercase text-muted-foreground tracking-wide mb-2">
                Experience
              </h3>
              <div className="space-y-3">
                {experiences.length > 0 ? (
                  experiences.map((item: any, idx: number) => (
                    <div
                      key={idx}
                      className="p-3 rounded-lg bg-white/5 border border-white/10"
                    >
                      <p className="font-semibold text-sm">
                        {item.title || item.role || "Role"}
                      </p>
                      <p className="text-xs text-muted-foreground">
                        {item.company || "Company not specified"}
                      </p>
                    </div>
                  ))
                ) : (
                  <p className="text-sm text-muted-foreground">
                    No experience entries
                  </p>
                )}
              </div>
            </section>

            <section>
              <h3 className="text-sm font-bold uppercase text-muted-foreground tracking-wide mb-2">
                Projects
              </h3>
              <div className="space-y-3">
                {projects.length > 0 ? (
                  projects.map((item: any, idx: number) => (
                    <div
                      key={idx}
                      className="p-3 rounded-lg bg-white/5 border border-white/10"
                    >
                      <p className="font-semibold text-sm">
                        {item.name || item.title || "Project"}
                      </p>
                      {(item.github_url || item.url || item.link) ? (
                        <a
                          href={item.github_url || item.url || item.link}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-xs text-primary hover:underline truncate block"
                        >
                          {item.github_url || item.url || item.link}
                        </a>
                      ) : (
                        <p className="text-xs text-muted-foreground">No link available</p>
                      )}
                    </div>
                  ))
                ) : (
                  <p className="text-sm text-muted-foreground">
                    No projects listed
                  </p>
                )}
              </div>
            </section>

            <section>
              <h3 className="text-sm font-bold uppercase text-muted-foreground tracking-wide mb-2">
                Education
              </h3>
              <div className="space-y-2">
                {education.length > 0 ? (
                  education.map((item: any, idx: number) => (
                    <p key={idx} className="text-sm">
                      {item.degree || item.name || "Education entry"}
                    </p>
                  ))
                ) : (
                  <p className="text-sm text-muted-foreground">
                    No education entries
                  </p>
                )}
              </div>
            </section>

            <section>
              <h3 className="text-sm font-bold uppercase text-muted-foreground tracking-wide mb-2">
                Certifications
              </h3>
              <div className="space-y-2">
                {certifications.length > 0 ? (
                  certifications.map((item: any, idx: number) => (
                    <p key={idx} className="text-sm">
                      {typeof item === "string"
                        ? item
                        : item.name || "Certification"}
                    </p>
                  ))
                ) : (
                  <p className="text-sm text-muted-foreground">
                    No certifications listed
                  </p>
                )}
              </div>
            </section>
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
};

const WeightSlider = ({
  label,
  helpText,
  value,
  onChange,
}: {
  label: string;
  helpText?: string;
  value: number;
  onChange: (v: number) => void;
}) => (
  <div className="space-y-3">
    <div className="flex justify-between text-xs font-bold">
      <span className="text-muted-foreground uppercase tracking-wider">
        {label}
      </span>
      <span className="text-primary">{value}</span>
    </div>
    <input
      type="range"
      min="0"
      max="100"
      value={value}
      onChange={(e) => onChange(parseInt(e.target.value, 10))}
      className="w-full h-1.5 bg-slate-800 rounded-full appearance-none cursor-pointer accent-primary"
    />
    {helpText && (
      <p className="text-[11px] text-muted-foreground">{helpText}</p>
    )}
  </div>
);

const CandidateRow = ({
  candidate,
  rank,
  onOpenProfile,
  onOpenResume,
  justificationPending,
}: {
  candidate: CandidateRankingResult;
  rank: number;
  onOpenProfile: (candidate: CandidateRankingResult) => void;
  onOpenResume: (resumeUploadId: string) => void;
  justificationPending: boolean;
}) => {
  const [isExpanded, setIsExpanded] = useState(rank === 1);
  const b = candidate.score_breakdown_json;

  const initials = candidate.candidate.full_name
    .split(" ")
    .slice(0, 2)
    .map((w) => w[0])
    .join("")
    .toUpperCase();

  return (
    <div className="border-b border-white/5 last:border-0">
      <div
        onClick={() => setIsExpanded(!isExpanded)}
        className="flex items-center gap-4 p-6 hover:bg-white/[0.02] transition-colors cursor-pointer group"
      >
        <div className="w-8 text-center font-bold text-muted-foreground">
          {rank}
        </div>
        <div className="flex-1 flex items-center gap-4">
          <div className="w-10 h-10 rounded-full bg-slate-800 flex items-center justify-center font-bold border border-white/10 group-hover:border-primary/50 transition-colors">
            {initials}
          </div>
          <div>
            <h4 className="font-bold text-sm flex items-center gap-2">
              {candidate.candidate.full_name}
              {candidate.candidate.is_low_confidence && (
                <TriangleAlert className="w-4 h-4 text-amber-400" />
              )}
            </h4>
            <p className="text-xs text-muted-foreground">
              {candidate.candidate.total_exp_years} years exp
            </p>
          </div>
        </div>

        <div className="hidden md:flex flex-col items-center gap-1 px-8 min-w-[100px]">
          <div
            className="text-sm font-bold"
            style={{
              color:
                candidate.final_score >= 70
                  ? "var(--score-high)"
                  : candidate.final_score >= 40
                    ? "var(--score-mid)"
                    : "var(--score-low)",
              fontFamily: "JetBrains Mono",
            }}
          >
            {candidate.final_score.toFixed(1)}
          </div>
          <div className="w-24 h-1.5 bg-white/5 rounded-full overflow-hidden">
            <div
              className="h-full"
              style={{
                width: `${candidate.final_score}%`,
                background:
                  candidate.final_score >= 70
                    ? "var(--score-high)"
                    : candidate.final_score >= 40
                      ? "var(--score-mid)"
                      : "var(--score-low)",
              }}
            />
          </div>
        </div>

        <button className="p-2 rounded-lg hover:bg-white/10 transition-colors">
          {isExpanded ? (
            <ChevronUp className="w-4 h-4" />
          ) : (
            <ChevronDown className="w-4 h-4" />
          )}
        </button>
      </div>

      <AnimatePresence>
        {isExpanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            className="overflow-hidden bg-white/[0.01]"
          >
            <div className="p-8 pt-4 grid grid-cols-1 lg:grid-cols-2 gap-8 border-t border-white/5">
              <div className="space-y-4">
                <div className="flex items-center gap-2 text-primary">
                  <BrainCircuit className="w-4 h-4" />
                  <h5 className="text-xs font-bold uppercase tracking-widest">
                    AI Justification
                  </h5>
                </div>
                {candidate.justification_text ? (
                  <p className="text-sm text-slate-300 leading-relaxed italic">
                    "{candidate.justification_text}"
                  </p>
                ) : justificationPending ? (
                  <div className="space-y-2">
                    <div className="h-3 w-full bg-white/10 rounded animate-pulse" />
                    <div className="h-3 w-3/4 bg-white/10 rounded animate-pulse" />
                    <p className="text-xs text-muted-foreground">
                      Generating justification...
                    </p>
                  </div>
                ) : (
                  <p className="text-sm text-muted-foreground italic">
                    Justification unavailable.
                  </p>
                )}
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div className="p-4 rounded-xl bg-white/5 border border-white/10">
                  <p className="text-[10px] font-bold text-muted-foreground uppercase mb-2">
                    Skill Match
                  </p>
                  <p className="text-xl font-bold">
                    {Number(b.skill_score || 0).toFixed(1)}
                  </p>
                </div>
                <div className="p-4 rounded-xl bg-white/5 border border-white/10">
                  <p className="text-[10px] font-bold text-muted-foreground uppercase mb-2">
                    Experience
                  </p>
                  <p className="text-xl font-bold">
                    {Number(b.exp_score || 0).toFixed(1)}
                  </p>
                </div>
                <div className="p-4 rounded-xl bg-white/5 border border-white/10">
                  <p className="text-[10px] font-bold text-muted-foreground uppercase mb-2">
                    Projects
                  </p>
                  <p className="text-xl font-bold">
                    {Number(b.projects_score || 0).toFixed(1)}
                  </p>
                </div>
                <div className="p-4 rounded-xl bg-white/5 border border-white/10">
                  <p className="text-[10px] font-bold text-muted-foreground uppercase mb-2">
                    Mandatory Skills
                  </p>
                  <p className="text-xl font-bold text-emerald-500">
                    {Number(b.matching_mandatory_skills || 0)}/
                    {Number(b.total_mandatory_skills || 0)}
                  </p>
                </div>
                <div className="p-4 rounded-xl bg-white/5 border border-white/10">
                  <p className="text-[10px] font-bold text-muted-foreground uppercase mb-2">
                    Semantic
                  </p>
                  <p className="text-xl font-bold">
                    {Number(b.semantic_score || 0).toFixed(1)}
                  </p>
                </div>
                <div className="flex items-center gap-2 px-2">
                  <button
                    type="button"
                    className="flex-1 bg-primary/10 text-primary border border-primary/20 py-2 rounded-lg text-xs font-bold hover:bg-primary hover:text-primary-foreground transition-all"
                    onClick={(e) => {
                      e.stopPropagation();
                      onOpenProfile(candidate);
                    }}
                  >
                    Profile
                  </button>
                  <button
                    type="button"
                    className="w-10 h-10 bg-white/5 border border-white/10 flex items-center justify-center rounded-lg hover:bg-white/10 transition-colors"
                    onClick={(e) => {
                      e.stopPropagation();
                      onOpenResume(candidate.candidate.resume_upload_id);
                    }}
                    title="View original resume"
                  >
                    <FileText className="w-4 h-4" />
                  </button>
                </div>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};

export const RankingDetail = () => {
  const { id: roleId } = useParams<{ id: string }>();

  const [role, setRole] = useState<JobRole | null>(null);
  const [jds, setJds] = useState<JobDescription[]>([]);
  const [selectedJdId, setSelectedJdId] = useState<string | null>(null);
  const [ranking, setRanking] = useState<JobDescriptionRankingResponse | null>(
    null,
  );
  const [_scoringConfig, setScoringConfig] = useState<ScoringConfig | null>(
    null,
  );

  const [loading, setLoading] = useState(true);
  const [rankingLoading, setRankingLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showConfig, setShowConfig] = useState(false);
  const [savingWeights, setSavingWeights] = useState(false);
  const [profileCandidate, setProfileCandidate] =
    useState<CandidateRankingResult | null>(null);
  const [editingJd, setEditingJd] = useState(false);
  const [jdDraft, setJdDraft] = useState("");
  const [savingJd, setSavingJd] = useState(false);
  const [justificationPolling, setJustificationPolling] = useState(false);
  const pollStartRef = useRef<number>(Date.now());
  const pollTimerRef = useRef<number | null>(null);

  const [weights, setWeights] = useState<ScoringConfigUpdate>({
    skill_match_weight: 40,
    exp_years_weight: 20,
    projects_weight: 20,
    prof_exp_weight: 15,
    certs_weight: 5,
  });

  useEffect(() => {
    if (!roleId) return;

    const fetchInitialData = async () => {
      setLoading(true);
      setError(null);
      try {
        const [rolesRes, jdsRes] = await Promise.all([
          api.get<JobRole[]>("/job-roles"),
          api.get<JobDescription[]>(`/job-roles/${roleId}/jds`),
        ]);

        const currentRole = rolesRes.data.find((r) => r.id === roleId) || null;
        setRole(currentRole);
        setJds(jdsRes.data);

        if (jdsRes.data.length > 0) {
          setSelectedJdId(jdsRes.data[0].id);
          setJdDraft(jdsRes.data[0].raw_text);
        }

        try {
          const configRes = await api.get<ScoringConfig>(
            `/job-roles/${roleId}/scoring-config`,
          );
          setScoringConfig(configRes.data);
          setWeights({
            skill_match_weight: configRes.data.skill_match_weight,
            exp_years_weight: configRes.data.exp_years_weight,
            projects_weight: configRes.data.projects_weight,
            prof_exp_weight: configRes.data.prof_exp_weight,
            certs_weight: configRes.data.certs_weight,
          });
        } catch {
          setScoringConfig(null);
        }
      } catch (err: any) {
        setError(err.response?.data?.detail || "Failed to load role data.");
      } finally {
        setLoading(false);
      }
    };

    fetchInitialData();
  }, [roleId]);

  const fetchRanking = useCallback(
    async (jdId: string, opts?: { silent?: boolean }) => {
      const silent = opts?.silent ?? false;
      if (!silent) setRankingLoading(true);
      try {
        const res = await api.get<JobDescriptionRankingResponse>(
          `/jd/${jdId}/ranking`,
        );
        setRanking(res.data);
      } catch (err: any) {
        setRanking(null);
        if (err.response?.status !== 404) {
          setError(err.response?.data?.detail || "Failed to fetch ranking.");
        }
      } finally {
        if (!silent) setRankingLoading(false);
      }
    },
    [],
  );

  useEffect(() => {
    if (selectedJdId) fetchRanking(selectedJdId);
  }, [selectedJdId, fetchRanking]);

  useEffect(() => {
    pollStartRef.current = Date.now();
    setJustificationPolling(false);
    if (pollTimerRef.current) {
      window.clearTimeout(pollTimerRef.current);
      pollTimerRef.current = null;
    }
  }, [selectedJdId]);

  useEffect(() => {
    if (!selectedJdId || !ranking || ranking.candidates.length === 0) {
      setJustificationPolling(false);
      return;
    }

    const pendingTop5 = ranking.candidates
      .slice(0, 5)
      .some((candidate) => !candidate.justification_text);

    if (!pendingTop5) {
      setJustificationPolling(false);
      return;
    }

    const elapsed = Date.now() - pollStartRef.current;
    if (elapsed >= 90_000) {
      setJustificationPolling(false);
      return;
    }

    setJustificationPolling(true);
    if (pollTimerRef.current) {
      window.clearTimeout(pollTimerRef.current);
    }

    pollTimerRef.current = window.setTimeout(() => {
      fetchRanking(selectedJdId, { silent: true });
    }, 5000);

    return () => {
      if (pollTimerRef.current) {
        window.clearTimeout(pollTimerRef.current);
        pollTimerRef.current = null;
      }
    };
  }, [ranking, selectedJdId, fetchRanking]);

  useEffect(() => {
    if (!selectedJdId) return;
    const selected = jds.find((jd) => jd.id === selectedJdId);
    if (selected) {
      setJdDraft(selected.raw_text);
    }
  }, [selectedJdId, jds]);

  const handleApplyWeights = async () => {
    if (!roleId) return;
    const total =
      weights.skill_match_weight +
      weights.exp_years_weight +
      weights.projects_weight +
      weights.prof_exp_weight +
      weights.certs_weight;

    if (total !== 100) {
      alert(`Weights must sum to 100. Current total: ${total}`);
      return;
    }

    setSavingWeights(true);
    try {
      const res = await api.put<ScoringConfig>(
        `/job-roles/${roleId}/scoring-config`,
        weights,
      );
      setScoringConfig(res.data);
      if (selectedJdId) await fetchRanking(selectedJdId);
    } catch (err: any) {
      alert(err.response?.data?.detail || "Failed to update weights.");
    } finally {
      setSavingWeights(false);
    }
  };

  const handleOpenResume = async (resumeUploadId: string) => {
    try {
      const res = await getResumeFileUrl(resumeUploadId);
      const url = res.data?.url;
      if (url) {
        window.open(url, "_blank", "noopener,noreferrer");
      }
    } catch (err: any) {
      alert(err.response?.data?.detail || "Unable to open resume file.");
    }
  };

  const handleSaveJd = async () => {
    if (!roleId) return;
    if (jdDraft.trim().length < 100) {
      alert("Job description must be at least 100 characters.");
      return;
    }

    setSavingJd(true);
    try {
      const createRes = await api.post<JobDescription>("/jd", {
        job_role_id: roleId,
        raw_text: jdDraft.trim(),
      });

      const jdsRes = await api.get<JobDescription[]>(
        `/job-roles/${roleId}/jds`,
      );
      setJds(jdsRes.data);
      setSelectedJdId(createRes.data.id);
      setEditingJd(false);
    } catch (err: any) {
      alert(err.response?.data?.detail || "Failed to save JD.");
    } finally {
      setSavingJd(false);
    }
  };

  const weightsTotal =
    weights.skill_match_weight +
    weights.exp_years_weight +
    weights.projects_weight +
    weights.prof_exp_weight +
    weights.certs_weight;

  const pendingJustifications =
    ranking?.candidates
      ?.slice(0, 5)
      .some((candidate) => !candidate.justification_text) ?? false;

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center py-32 gap-4">
        <Loader2 className="w-8 h-8 text-primary animate-spin" />
        <p className="text-muted-foreground text-sm">Loading role data...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center py-32 gap-4">
        <div className="w-16 h-16 rounded-full bg-red-500/10 flex items-center justify-center">
          <AlertCircle className="w-8 h-8 text-red-400" />
        </div>
        <p className="text-red-400 text-sm text-center max-w-md">{error}</p>
        <Link
          to="/jobs"
          className="text-sm text-primary hover:underline font-medium"
        >
          Back to Job Roles
        </Link>
      </div>
    );
  }

  return (
    <div className="space-y-8 animate-in pb-20">
      <div className="flex items-center gap-4">
        <Link
          to="/jobs"
          className="p-2 rounded-xl bg-white/5 hover:bg-white/10 transition-colors group"
        >
          <ArrowLeft className="w-5 h-5 group-hover:-translate-x-1 transition-transform" />
        </Link>
        <div>
          <nav className="text-xs text-muted-foreground mb-1">
            <Link to="/jobs" className="hover:text-primary">
              Job Roles
            </Link>{" "}
            / <span>{role?.title || "Role"}</span>
          </nav>
          <h1 className="text-3xl font-bold">{role?.title || "Job Role"}</h1>
          <p className="text-sm text-muted-foreground">
            Candidate Ranking & Justification
          </p>
        </div>
        <div className="ml-auto flex items-center gap-3">
          <Link
            to={`/jobs/${roleId}/upload`}
            className="p-3 rounded-xl border border-white/10 bg-white/5 text-foreground hover:bg-white/10 transition-all flex items-center gap-2"
          >
            <Upload className="w-5 h-5" />
            <span className="text-sm font-bold hidden md:block">Upload</span>
          </Link>
          <button
            onClick={() => setShowConfig((prev) => !prev)}
            className={`p-3 rounded-xl border transition-all flex items-center gap-2 ${showConfig ? "bg-primary border-primary text-primary-foreground" : "bg-white/5 border-white/10 text-foreground hover:bg-white/10"}`}
          >
            <Settings2 className="w-5 h-5" />
            <span className="text-sm font-bold hidden md:block">
              Configure Weights
            </span>
          </button>
        </div>
      </div>

      {jds.length > 0 && (
        <div className="space-y-3">
          <div className="flex items-center gap-4">
            <label className="text-xs font-bold text-muted-foreground uppercase tracking-wider">
              Job Description
            </label>
            <select
              value={selectedJdId || ""}
              onChange={(e) => {
                setSelectedJdId(e.target.value);
                setEditingJd(false);
              }}
              className="bg-white/5 border border-border rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50 transition-all flex-1 max-w-md appearance-none cursor-pointer"
            >
              {jds.map((jd) => (
                <option key={jd.id} value={jd.id} className="bg-slate-900">
                  {jd.raw_text.substring(0, 60)}... ({jd.status})
                </option>
              ))}
            </select>
            <button
              type="button"
              className="text-xs px-3 py-2 rounded-md border border-white/10 hover:bg-white/10"
              onClick={() => {
                setJdDraft("");
                setEditingJd(true);
              }}
            >
              Create JD
            </button>
          </div>

          {!editingJd ? (
            <div className="rounded-xl border border-white/10 bg-white/5 p-4 flex items-start justify-between gap-3">
              <p className="text-sm text-muted-foreground line-clamp-2">
                {jdDraft.slice(0, 200)}
                {jdDraft.length > 200 ? "..." : ""}
              </p>
              <button
                type="button"
                className="text-xs px-3 py-1.5 rounded-md border border-white/10 hover:bg-white/10"
                onClick={() => setEditingJd(true)}
              >
                Edit JD
              </button>
            </div>
          ) : (
            <div className="rounded-xl border border-white/10 bg-white/5 p-4 space-y-3">
              <textarea
                value={jdDraft}
                onChange={(e) => setJdDraft(e.target.value)}
                rows={8}
                minLength={100}
                className="w-full bg-black/30 border border-white/10 rounded-xl px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50 resize-y"
                placeholder="Paste the full job description here..."
              />
              <div className="flex items-center gap-2 justify-end">
                <button
                  type="button"
                  className="px-3 py-2 text-sm rounded-md border border-white/10 hover:bg-white/10"
                  onClick={() => setEditingJd(false)}
                >
                  Cancel
                </button>
                <button
                  type="button"
                  className="px-3 py-2 text-sm rounded-md bg-primary text-primary-foreground disabled:opacity-50"
                  onClick={handleSaveJd}
                  disabled={savingJd || jdDraft.trim().length < 100}
                >
                  {savingJd ? "Saving..." : "Save JD"}
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {showConfig && (
        <div className="glass-card rounded-3xl p-6 border border-primary/30">
          <div className="flex items-center gap-2 mb-6">
            <div className="w-8 h-8 bg-primary/10 rounded-lg flex items-center justify-center text-primary">
              <Settings2 className="w-4 h-4" />
            </div>
            <h3 className="font-bold">Scoring Weights</h3>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <WeightSlider
              label="Skills Match"
              value={weights.skill_match_weight}
              onChange={(v) =>
                setWeights({ ...weights, skill_match_weight: v })
              }
            />
            <WeightSlider
              label="Experience (Total Years)"
              helpText="Compares candidate total years against JD minimum years."
              value={weights.exp_years_weight}
              onChange={(v) => setWeights({ ...weights, exp_years_weight: v })}
            />
            <WeightSlider
              label="Projects"
              value={weights.projects_weight}
              onChange={(v) => setWeights({ ...weights, projects_weight: v })}
            />
            <WeightSlider
              label="Professional Experience"
              helpText="Scores duration in professional-role entries only."
              value={weights.prof_exp_weight}
              onChange={(v) => setWeights({ ...weights, prof_exp_weight: v })}
            />
            <WeightSlider
              label="Certifications"
              value={weights.certs_weight}
              onChange={(v) => setWeights({ ...weights, certs_weight: v })}
            />
          </div>

          <div
            className={`mt-6 p-4 rounded-xl border ${weightsTotal === 100 ? "bg-primary/5 border-primary/20" : "bg-red-500/5 border-red-500/20"}`}
          >
            <p
              className={`text-xs font-bold ${weightsTotal === 100 ? "text-primary" : "text-red-400"}`}
            >
              Total: {weightsTotal}/100{" "}
              {weightsTotal !== 100 && "(must equal 100)"}
            </p>
            <p className="text-[11px] text-muted-foreground mt-1">
              Tip: "Experience" is total years; "Professional Experience"
              focuses on professional-role duration.
            </p>
          </div>

          <button
            onClick={handleApplyWeights}
            disabled={weightsTotal !== 100 || savingWeights}
            className="bg-primary text-primary-foreground font-bold py-3 px-6 rounded-xl mt-4 transition-all disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
          >
            {savingWeights && <Loader2 className="w-4 h-4 animate-spin" />}
            {savingWeights ? "Applying..." : "Save & Re-rank"}
          </button>
        </div>
      )}

      {jds.length === 0 && (
        <div className="glass-card rounded-3xl p-6 border border-white/10 space-y-4">
          <div className="flex items-center gap-2">
            <FolderOpen className="w-5 h-5 text-muted-foreground" />
            <p className="text-sm text-muted-foreground">
              No job descriptions found yet. Create one to start ranking
              candidates.
            </p>
          </div>
          <textarea
            value={jdDraft}
            onChange={(e) => setJdDraft(e.target.value)}
            rows={8}
            minLength={100}
            className="w-full bg-black/30 border border-white/10 rounded-xl px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50 resize-y"
            placeholder="Paste the full job description here..."
          />
          <div className="flex justify-end">
            <button
              type="button"
              className="px-3 py-2 text-sm rounded-md bg-primary text-primary-foreground disabled:opacity-50"
              onClick={handleSaveJd}
              disabled={savingJd || jdDraft.trim().length < 100}
            >
              {savingJd ? "Saving..." : "Create JD"}
            </button>
          </div>
        </div>
      )}

      {jds.length > 0 && (
        <div className="glass-card rounded-3xl overflow-hidden shadow-2xl">
          <div className="bg-white/5 px-8 py-4 flex justify-between items-center border-b border-white/5 font-bold text-xs text-muted-foreground uppercase tracking-widest">
            <span>Candidate Match Pipeline</span>
            <div className="flex items-center gap-3">
              {pendingJustifications && (
                <button
                  type="button"
                  className="text-[11px] normal-case inline-flex items-center gap-1 px-2 py-1 rounded border border-white/10 hover:bg-white/10"
                  onClick={() =>
                    selectedJdId && fetchRanking(selectedJdId, { silent: true })
                  }
                >
                  <RefreshCw className="w-3 h-3" />
                  Refresh Justifications
                </button>
              )}
              <span>Sorted by AI Score</span>
            </div>
          </div>

          {rankingLoading && (
            <div className="flex items-center justify-center py-16 gap-3">
              <Loader2 className="w-5 h-5 text-primary animate-spin" />
              <p className="text-muted-foreground text-sm">
                Fetching rankings...
              </p>
            </div>
          )}

          {!rankingLoading && ranking && ranking.candidates.length > 0 && (
            <div className="divide-y divide-white/5">
              {ranking.candidates.map((candidate, idx) => (
                <CandidateRow
                  key={candidate.candidate.id}
                  candidate={candidate}
                  rank={idx + 1}
                  onOpenProfile={(row) => setProfileCandidate(row)}
                  onOpenResume={handleOpenResume}
                  justificationPending={
                    idx < 5 &&
                    !candidate.justification_text &&
                    justificationPolling
                  }
                />
              ))}
            </div>
          )}

          {!rankingLoading && (!ranking || ranking.candidates.length === 0) && (
            <div className="flex flex-col items-center justify-center py-16 gap-3">
              <FolderOpen className="w-6 h-6 text-muted-foreground" />
              <p className="text-muted-foreground text-sm">
                No candidates ranked yet.
              </p>
              <Link
                to={`/jobs/${roleId}/upload`}
                className="text-primary text-sm hover:underline"
              >
                Upload resumes
              </Link>
            </div>
          )}

          {!rankingLoading && ranking && ranking.candidates.length === 0 && (
            <p className="text-sm text-muted-foreground text-center pb-6">
              No candidates were ranked. Ensure resumes are fully parsed before
              running ranking.
            </p>
          )}

          {!rankingLoading &&
            ranking &&
            ranking.candidates.length > 0 &&
            ranking.candidates[0].ranked_at && (
              <p className="text-xs text-muted-foreground px-8 py-4 border-t border-white/5">
                Ranked against JD submitted{" "}
                {new Date(ranking.candidates[0].ranked_at).toLocaleString()}
              </p>
            )}
        </div>
      )}

      <ProfilePanel
        candidate={profileCandidate}
        onClose={() => setProfileCandidate(null)}
      />
    </div>
  );
};
