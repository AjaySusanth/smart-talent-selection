import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  Upload,
  Loader2,
  AlertCircle,
  FileWarning,
  CheckCircle2,
  Clock3,
} from "lucide-react";
import {
  api,
  deleteResumeUpload,
  getResumeStatus,
  listRoleResumes,
  retryResumeParsing,
  uploadResumes,
} from "../lib/api";
import type {
  BatchUploadResponse,
  JobRole,
  ResumeUploadListItem,
  ResumeUploadStatus,
  UploadStatusResponse,
} from "../types";

const ALLOWED_TYPES = [
  "application/pdf",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  "image/jpeg",
  "image/png",
];

const MAX_BYTES = 10 * 1024 * 1024;
const TERMINAL = new Set<ResumeUploadStatus>(["parsed", "failed"]);

const STATUS_CONFIG: Record<
  ResumeUploadStatus | "uploading",
  { color: string; label: string; progress: number }
> = {
  uploading: { color: "var(--accent)", label: "Uploading...", progress: 15 },
  uploaded: { color: "var(--accent)", label: "Uploaded", progress: 25 },
  queued: { color: "var(--warning)", label: "Queued", progress: 40 },
  parsing: { color: "var(--warning)", label: "Parsing...", progress: 70 },
  parsed: { color: "var(--success)", label: "Parsed", progress: 100 },
  failed: { color: "var(--error)", label: "Failed", progress: 100 },
};

type FileState = {
  id: string;
  original_name: string;
  status: ResumeUploadStatus | "uploading";
  error_message: string | null;
  guidance_message?: string | null;
  uploaded_at?: string;
  startedAt: number;
  nextPollMs: number;
};

const validateFile = (file: File): string | null => {
  if (!ALLOWED_TYPES.includes(file.type)) {
    return "Unsupported file type. Use PDF, DOCX, JPG, or PNG.";
  }
  if (file.size > MAX_BYTES) {
    return `File too large (${(file.size / 1048576).toFixed(1)} MB). Max 10 MB.`;
  }
  return null;
};

const isLikelyLlmFailure = (
  errorMessage: string | null | undefined,
): boolean => {
  if (!errorMessage) return false;
  const text = errorMessage.toLowerCase();
  return (
    text.includes("validation error for candidateprofile") ||
    text.includes("unparseable json") ||
    text.includes("json") ||
    text.includes("gemini") ||
    text.includes("groq") ||
    text.includes("llm")
  );
};

const getGuidanceMessage = (
  errorMessage: string | null | undefined,
): string | null => {
  if (!errorMessage) return null;
  if (isLikelyLlmFailure(errorMessage)) {
    return "This looks like an AI extraction issue. Please retry parsing.";
  }
  return null;
};

export const UploadPage = () => {
  const { id: roleId } = useParams<{ id: string }>();

  const [role, setRole] = useState<JobRole | null>(null);
  const [loadingRole, setLoadingRole] = useState(true);
  const [loadingExisting, setLoadingExisting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [files, setFiles] = useState<FileState[]>([]);
  const [uploading, setUploading] = useState(false);
  const [retryingIds, setRetryingIds] = useState<Set<string>>(new Set());
  const [deletingIds, setDeletingIds] = useState<Set<string>>(new Set());
  const [queueErrors, setQueueErrors] = useState<string[]>([]);

  const timersRef = useRef<Map<string, number>>(new Map());

  const hydrateRole = useCallback(async () => {
    if (!roleId) return;
    setLoadingRole(true);
    setError(null);
    try {
      const response = await api.get<JobRole[]>("/job-roles");
      const currentRole = response.data.find((r) => r.id === roleId) || null;
      setRole(currentRole);
    } catch (err: any) {
      setError(err.response?.data?.detail || "Failed to load job role.");
    } finally {
      setLoadingRole(false);
    }
  }, [roleId]);

  const hydrateExistingUploads = useCallback(async () => {
    if (!roleId) return;
    setLoadingExisting(true);
    try {
      const response = await listRoleResumes(roleId);
      const existing: FileState[] = (
        response.data as ResumeUploadListItem[]
      ).map((item) => ({
        id: item.id,
        original_name: item.original_name,
        status: item.status,
        error_message: item.error_message,
        uploaded_at: item.uploaded_at,
        startedAt: Date.now(),
        nextPollMs: 3000,
        guidance_message: getGuidanceMessage(item.error_message),
      }));

      setFiles((prev) => {
        const map = new Map(prev.map((f) => [f.id, f]));
        existing.forEach((e) => {
          if (!map.has(e.id)) map.set(e.id, e);
        });
        return Array.from(map.values()).sort((a, b) =>
          (b.uploaded_at || "").localeCompare(a.uploaded_at || ""),
        );
      });
    } catch (err: any) {
      setError(err.response?.data?.detail || "Failed to load upload history.");
    } finally {
      setLoadingExisting(false);
    }
  }, [roleId]);

  useEffect(() => {
    hydrateRole();
    hydrateExistingUploads();
    return () => {
      timersRef.current.forEach((timer) => window.clearTimeout(timer));
      timersRef.current.clear();
    };
  }, [hydrateRole, hydrateExistingUploads]);

  const schedulePoll = useCallback(
    (uploadId: string, waitMs: number) => {
      if (!roleId) return;

      const prev = timersRef.current.get(uploadId);
      if (prev) window.clearTimeout(prev);

      const timer = window.setTimeout(async () => {
        timersRef.current.delete(uploadId);
        try {
          const response = await getResumeStatus(uploadId);
          const payload = response.data as UploadStatusResponse;

          setFiles((current) =>
            current.map((file) => {
              if (file.id !== uploadId) return file;

              const elapsed = Date.now() - file.startedAt;
              const timeoutReached = elapsed > 5 * 60 * 1000;
              if (timeoutReached && !TERMINAL.has(payload.status)) {
                return {
                  ...file,
                  status: "failed",
                  error_message: "Processing timeout after 5 minutes.",
                  nextPollMs: file.nextPollMs,
                };
              }

              const nextPollMs = Math.min(file.nextPollMs + 2000, 15000);
              return {
                ...file,
                original_name: payload.original_name,
                status: payload.status,
                error_message: payload.error_message,
                guidance_message: getGuidanceMessage(payload.error_message),
                nextPollMs,
              };
            }),
          );
        } catch {
          setFiles((current) =>
            current.map((file) =>
              file.id === uploadId
                ? {
                    ...file,
                    nextPollMs: Math.min(file.nextPollMs + 2000, 15000),
                  }
                : file,
            ),
          );
        }
      }, waitMs);

      timersRef.current.set(uploadId, timer);
    },
    [roleId],
  );

  useEffect(() => {
    files.forEach((file) => {
      if (file.status === "uploading" || TERMINAL.has(file.status)) {
        const currentTimer = timersRef.current.get(file.id);
        if (currentTimer) {
          window.clearTimeout(currentTimer);
          timersRef.current.delete(file.id);
        }
        return;
      }
      if (!timersRef.current.has(file.id)) {
        schedulePoll(file.id, file.nextPollMs);
      }
    });
  }, [files, schedulePoll]);

  const onPickFiles = (list: FileList | null) => {
    if (!list) return;
    const picked = Array.from(list);
    const errors: string[] = [];
    const valid: File[] = [];

    picked.forEach((file) => {
      const reason = validateFile(file);
      if (reason) {
        errors.push(`${file.name}: ${reason}`);
      } else {
        valid.push(file);
      }
    });

    setQueueErrors(errors);

    if (valid.length === 0 || !roleId) return;

    const optimistic = valid.map((file, idx) => ({
      id: `temp-${Date.now()}-${idx}`,
      original_name: file.name,
      status: "uploading" as const,
      error_message: null,
      startedAt: Date.now(),
      nextPollMs: 3000,
    }));

    setFiles((prev) => [...optimistic, ...prev]);

    (async () => {
      setUploading(true);
      try {
        const response = await uploadResumes(roleId, valid);
        const payload = response.data as BatchUploadResponse;

        setFiles((prev) => {
          const withoutTemps = prev.filter((f) => !f.id.startsWith("temp-"));

          const uploaded = payload.uploaded.map((u) => ({
            id: u.id,
            original_name: u.original_name,
            status: (u.status || "uploaded") as ResumeUploadStatus,
            error_message: u.error_message,
            startedAt: Date.now(),
            nextPollMs: 3000,
            guidance_message: getGuidanceMessage(u.error_message),
          }));

          const failed = payload.failed.map((u, idx) => ({
            id: `failed-${Date.now()}-${idx}`,
            original_name: u.original_name,
            status: "failed" as ResumeUploadStatus,
            error_message: u.error_message,
            startedAt: Date.now(),
            nextPollMs: 3000,
            guidance_message: getGuidanceMessage(u.error_message),
          }));

          return [...uploaded, ...failed, ...withoutTemps];
        });
      } catch (err: any) {
        setError(err.response?.data?.detail || "Upload failed.");
        setFiles((prev) => prev.filter((f) => !f.id.startsWith("temp-")));
      } finally {
        setUploading(false);
      }
    })();
  };

  const handleRetry = async (uploadId: string) => {
    setRetryingIds((prev) => new Set(prev).add(uploadId));
    try {
      await retryResumeParsing(uploadId);
      setFiles((current) =>
        current.map((file) =>
          file.id === uploadId
            ? {
                ...file,
                status: "queued",
                error_message: null,
                guidance_message: null,
                startedAt: Date.now(),
                nextPollMs: 3000,
              }
            : file,
        ),
      );
    } catch (err: any) {
      setError(err.response?.data?.detail || "Failed to retry parsing.");
    } finally {
      setRetryingIds((prev) => {
        const next = new Set(prev);
        next.delete(uploadId);
        return next;
      });
    }
  };

  const handleDelete = async (uploadId: string) => {
    const confirmed = window.confirm("Delete this failed resume upload?");
    if (!confirmed) return;

    setDeletingIds((prev) => new Set(prev).add(uploadId));
    try {
      await deleteResumeUpload(uploadId);
      setFiles((current) => current.filter((file) => file.id !== uploadId));
    } catch (err: any) {
      setError(err.response?.data?.detail || "Failed to delete resume.");
    } finally {
      setDeletingIds((prev) => {
        const next = new Set(prev);
        next.delete(uploadId);
        return next;
      });
    }
  };

  const counts = useMemo(() => {
    let parsed = 0;
    let processing = 0;
    let failed = 0;

    files.forEach((f) => {
      if (f.status === "parsed") parsed += 1;
      else if (f.status === "failed") failed += 1;
      else processing += 1;
    });

    return { parsed, processing, failed, total: files.length };
  }, [files]);

  const allDone = counts.total > 0 && counts.processing === 0;

  if (loadingRole) {
    return (
      <div className="flex items-center justify-center py-24 gap-3">
        <Loader2 className="w-6 h-6 text-primary animate-spin" />
        <p className="text-muted-foreground text-sm">
          Loading upload workspace...
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-8 animate-in pb-16">
      <div>
        <nav className="text-xs text-muted-foreground mb-2">
          <Link to="/jobs" className="hover:text-primary">
            Job Roles
          </Link>{" "}
          /{" "}
          <Link to={`/jobs/${roleId}/rank`} className="hover:text-primary">
            {role?.title || "Role"}
          </Link>{" "}
          / <span>Upload</span>
        </nav>
        <h1 className="text-3xl font-bold">Upload Resumes</h1>
        <p className="text-muted-foreground mt-2">
          Upload PDF, DOCX, JPG, or PNG files up to 10 MB.
        </p>
      </div>

      {error && (
        <div className="flex items-center gap-2 text-sm text-red-400 bg-red-500/10 border border-red-500/20 rounded-xl p-3">
          <AlertCircle className="w-4 h-4" />
          <span>{error}</span>
        </div>
      )}

      <section className="glass-card rounded-3xl p-6 border border-white/10">
        <label className="block border-2 border-dashed border-white/20 rounded-2xl p-10 text-center cursor-pointer hover:border-primary/40 transition-colors">
          <Upload className="w-10 h-10 mx-auto text-primary mb-3" />
          <p className="font-semibold">Drop files here or click to browse</p>
          <p className="text-xs text-muted-foreground mt-2">
            PDF, DOCX, JPG, PNG · max 10 MB each
          </p>
          <input
            type="file"
            className="hidden"
            multiple
            onChange={(e) => onPickFiles(e.target.files)}
            accept=".pdf,.docx,.jpg,.jpeg,.png,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,image/jpeg,image/png"
          />
        </label>

        {uploading && (
          <div className="mt-4 flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="w-4 h-4 animate-spin" />
            Uploading selected files...
          </div>
        )}

        {queueErrors.length > 0 && (
          <div className="mt-4 rounded-xl border border-amber-400/30 bg-amber-400/10 p-3 text-sm space-y-1">
            <div className="flex items-center gap-2 font-semibold text-amber-300">
              <FileWarning className="w-4 h-4" />
              Some files were skipped
            </div>
            {queueErrors.map((item) => (
              <p key={item} className="text-amber-200">
                {item}
              </p>
            ))}
          </div>
        )}
      </section>

      <section className="glass-card rounded-3xl p-6 border border-white/10 space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-xl font-bold">Processing Status</h2>
          <div className="text-sm text-muted-foreground">
            {counts.parsed} / {counts.total} parsed · {counts.processing}{" "}
            processing · {counts.failed} failed
          </div>
        </div>

        {loadingExisting && files.length === 0 ? (
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="w-4 h-4 animate-spin" />
            Loading previous uploads...
          </div>
        ) : files.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No uploads yet for this role.
          </p>
        ) : (
          <div className="space-y-3">
            {files.map((file) => {
              const cfg = STATUS_CONFIG[file.status];
              return (
                <div
                  key={file.id}
                  className="rounded-xl border border-white/10 p-4 bg-white/5"
                >
                  <div className="flex items-start justify-between gap-3 mb-2">
                    <p className="text-sm font-medium truncate">
                      {file.original_name}
                    </p>
                    <span
                      className="text-xs font-semibold"
                      style={{ color: cfg.color }}
                    >
                      {cfg.label}
                    </span>
                  </div>

                  <div className="h-2 bg-black/30 rounded-full overflow-hidden">
                    <div
                      className="h-full transition-all duration-500"
                      style={{
                        width: `${cfg.progress}%`,
                        background: cfg.color,
                      }}
                    />
                  </div>

                  <div className="text-xs text-muted-foreground mt-2 flex items-center gap-2">
                    {file.status === "parsing" && (
                      <Clock3 className="w-3 h-3" />
                    )}
                    {file.status === "parsed" && (
                      <CheckCircle2 className="w-3 h-3 text-emerald-400" />
                    )}
                    <span>
                      {file.status === "parsing"
                        ? "Extracting text and structure..."
                        : file.error_message || cfg.label}
                    </span>
                  </div>

                  {file.status === "failed" && file.guidance_message && (
                    <p className="text-xs text-amber-300 mt-2">
                      {file.guidance_message}
                    </p>
                  )}

                  {file.status === "failed" &&
                    !file.id.startsWith("failed-") && (
                      <div className="mt-3 flex items-center gap-2">
                        <button
                          type="button"
                          onClick={() => handleRetry(file.id)}
                          disabled={retryingIds.has(file.id)}
                          className="text-xs px-2.5 py-1.5 rounded-md border border-primary/30 bg-primary/10 text-primary hover:bg-primary hover:text-primary-foreground disabled:opacity-50"
                        >
                          {retryingIds.has(file.id)
                            ? "Retrying..."
                            : "Retry parsing"}
                        </button>
                        <button
                          type="button"
                          onClick={() => handleDelete(file.id)}
                          disabled={deletingIds.has(file.id)}
                          className="text-xs px-2.5 py-1.5 rounded-md border border-red-500/30 bg-red-500/10 text-red-300 hover:bg-red-500/20 disabled:opacity-50"
                        >
                          {deletingIds.has(file.id) ? "Deleting..." : "Delete"}
                        </button>
                      </div>
                    )}
                </div>
              );
            })}
          </div>
        )}

        {allDone && counts.parsed > 0 && (
          <div className="rounded-xl border border-emerald-500/30 bg-emerald-500/10 p-4 text-sm">
            <p className="text-emerald-300 font-semibold">
              All files processed - ready to rank.
            </p>
            <Link
              to={`/jobs/${roleId}/rank`}
              className="text-primary hover:underline mt-2 inline-block"
            >
              Go to Ranking page
            </Link>
          </div>
        )}
      </section>
    </div>
  );
};
