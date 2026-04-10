import { useState, useEffect, useCallback } from "react";
import {
  Plus,
  Search,
  Filter,
  MoreHorizontal,
  Users,
  TrendingUp,
  Loader2,
  AlertCircle,
  FolderOpen,
  X,
  Upload,
} from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { Link } from "react-router-dom";
import { api, updateJobRole, deactivateJobRole } from "../lib/api";
import type { JobRole, JobRoleCreate, JobRoleUpdate } from "../types";

type RoleCardProps = {
  role: JobRole;
  index: number;
  onEdit: (role: JobRole) => void;
  onDeactivate: (role: JobRole) => void;
};

const JobRoleCard = ({ role, index, onEdit, onDeactivate }: RoleCardProps) => {
  const [menuOpen, setMenuOpen] = useState(false);

  return (
    <motion.div
      initial={{ opacity: 0, x: -20 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ delay: index * 0.06 }}
      className="relative"
    >
      <Link
        to={`/jobs/${role.id}/rank`}
        className="glass-card block rounded-2xl p-6 group hover:border-primary/50 transition-all duration-300"
      >
        <div className="flex justify-between items-start mb-6">
          <div className="w-12 h-12 bg-primary/10 rounded-xl flex items-center justify-center text-primary border border-primary/20 group-hover:scale-110 transition-transform">
            <TrendingUp className="w-6 h-6" />
          </div>

          <div className="relative">
            <button
              type="button"
              onClick={(e) => {
                e.preventDefault();
                e.stopPropagation();
                setMenuOpen((prev) => !prev);
              }}
              className="text-muted-foreground hover:text-foreground p-2 rounded-lg hover:bg-white/10"
              aria-label="Role actions"
            >
              <MoreHorizontal className="w-5 h-5" />
            </button>

            {menuOpen && (
              <div
                className="absolute right-0 top-11 w-40 rounded-xl border border-border bg-slate-900/95 backdrop-blur px-1 py-1 z-20"
                onClick={(e) => {
                  e.preventDefault();
                  e.stopPropagation();
                }}
              >
                <button
                  type="button"
                  className="w-full text-left px-3 py-2 text-sm rounded-lg hover:bg-white/10"
                  onClick={() => {
                    setMenuOpen(false);
                    onEdit(role);
                  }}
                >
                  Edit role
                </button>
                <button
                  type="button"
                  className="w-full text-left px-3 py-2 text-sm rounded-lg text-red-400 hover:bg-red-500/10"
                  onClick={() => {
                    setMenuOpen(false);
                    onDeactivate(role);
                  }}
                >
                  Deactivate
                </button>
              </div>
            )}
          </div>
        </div>

        <h3 className="text-xl font-bold mb-2 group-hover:text-primary transition-colors">
          {role.title}
        </h3>
        <p className="text-sm text-muted-foreground line-clamp-2 mb-6 h-10">
          {role.description || "No description provided for this job role."}
        </p>

        <div className="flex items-center justify-between pt-6 border-t border-white/5">
          <div className="flex items-center gap-2 text-sm">
            <Users className="w-4 h-4 text-muted-foreground" />
            <span className="font-semibold">{role.resume_count}</span>
            <span className="text-muted-foreground text-xs uppercase tracking-wider">
              Candidates
            </span>
          </div>
          <div className="flex items-center gap-2">
            <Link
              to={`/jobs/${role.id}/upload`}
              onClick={(e) => e.stopPropagation()}
              className="inline-flex items-center gap-1 text-xs px-2 py-1 rounded-md bg-white/5 border border-white/10 hover:bg-white/10"
            >
              <Upload className="w-3 h-3" />
              Upload
            </Link>
            <span className="text-xs text-primary font-semibold">Rank</span>
          </div>
        </div>
      </Link>
    </motion.div>
  );
};

export const JobRoles = () => {
  const [roles, setRoles] = useState<JobRole[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [showInactive, setShowInactive] = useState(false);

  const [showCreateModal, setShowCreateModal] = useState(false);
  const [createForm, setCreateForm] = useState<JobRoleCreate>({
    title: "",
    description: "",
  });
  const [creating, setCreating] = useState(false);

  const [editingRole, setEditingRole] = useState<JobRole | null>(null);
  const [editForm, setEditForm] = useState<JobRoleUpdate>({
    title: "",
    description: "",
  });
  const [savingEdit, setSavingEdit] = useState(false);

  const fetchRoles = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await api.get<JobRole[]>("/job-roles");
      setRoles(response.data);
    } catch (err: any) {
      setError(
        err.response?.data?.detail ||
          "Failed to fetch job roles. Is the backend running?",
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchRoles();
  }, [fetchRoles]);

  const handleCreateRole = async () => {
    if (!createForm.title.trim()) return;
    setCreating(true);
    try {
      await api.post("/job-roles", createForm);
      setShowCreateModal(false);
      setCreateForm({ title: "", description: "" });
      await fetchRoles();
    } catch (err: any) {
      setError(err.response?.data?.detail || "Failed to create job role.");
    } finally {
      setCreating(false);
    }
  };

  const openEditModal = (role: JobRole) => {
    setEditingRole(role);
    setEditForm({ title: role.title, description: role.description ?? "" });
  };

  const handleSaveEdit = async () => {
    if (!editingRole) return;
    setSavingEdit(true);
    try {
      await updateJobRole(editingRole.id, {
        title: editForm.title,
        description: editForm.description ?? null,
      });
      setEditingRole(null);
      await fetchRoles();
    } catch (err: any) {
      setError(err.response?.data?.detail || "Failed to update job role.");
    } finally {
      setSavingEdit(false);
    }
  };

  const handleDeactivate = async (role: JobRole) => {
    const confirmed = window.confirm(`Deactivate role "${role.title}"?`);
    if (!confirmed) return;

    try {
      await deactivateJobRole(role.id);
      await fetchRoles();
    } catch (err: any) {
      setError(err.response?.data?.detail || "Failed to deactivate job role.");
    }
  };

  const filteredRoles = roles
    .filter((r) => showInactive || r.is_active)
    .filter(
      (r) =>
        r.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
        (r.description &&
          r.description.toLowerCase().includes(searchQuery.toLowerCase())),
    );

  return (
    <div className="space-y-8 animate-in">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-4xl font-bold tracking-tight">Job Roles</h1>
          <p className="text-muted-foreground mt-2">
            Manage and rank candidates for your active hiring pipelines.
          </p>
        </div>
        <button
          onClick={() => setShowCreateModal(true)}
          className="bg-primary text-primary-foreground px-6 py-3 rounded-xl font-bold flex items-center gap-2 shadow-[0_0_20px_rgba(16,185,129,0.2)] hover:shadow-[0_0_30px_rgba(16,185,129,0.4)] transition-all"
        >
          <Plus className="w-5 h-5" />
          Create New Role
        </button>
      </div>

      <div className="flex flex-col md:flex-row gap-4">
        <div className="relative flex-1">
          <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <input
            type="text"
            placeholder="Search roles..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full bg-white/5 border border-border rounded-xl pl-12 pr-4 py-3 focus:outline-none focus:ring-2 focus:ring-primary/50 transition-all"
          />
        </div>
        <button
          type="button"
          onClick={() => setShowInactive((prev) => !prev)}
          className="px-4 py-3 rounded-xl bg-white/5 border border-border flex items-center gap-2 hover:bg-white/10 transition-colors"
        >
          <Filter className="w-4 h-4" />
          <span>{showInactive ? "Showing All" : "Active Only"}</span>
        </button>
      </div>

      {loading && (
        <div className="flex flex-col items-center justify-center py-20 gap-4">
          <Loader2 className="w-8 h-8 text-primary animate-spin" />
          <p className="text-muted-foreground text-sm">Loading job roles...</p>
        </div>
      )}

      {!loading && error && (
        <div className="flex flex-col items-center justify-center py-20 gap-4">
          <div className="w-16 h-16 rounded-full bg-red-500/10 flex items-center justify-center">
            <AlertCircle className="w-8 h-8 text-red-400" />
          </div>
          <p className="text-red-400 text-sm text-center max-w-md">{error}</p>
          <button
            onClick={fetchRoles}
            className="text-sm text-primary hover:underline font-medium"
          >
            Try again
          </button>
        </div>
      )}

      {!loading && !error && filteredRoles.length === 0 && (
        <div className="flex flex-col items-center justify-center py-20 gap-4">
          <div className="w-16 h-16 rounded-full bg-white/5 flex items-center justify-center">
            <FolderOpen className="w-8 h-8 text-muted-foreground" />
          </div>
          <p className="text-muted-foreground text-sm">
            {searchQuery
              ? "No roles match your search."
              : "No job roles yet. Create your first one to get started."}
          </p>
          {!searchQuery && (
            <button
              onClick={() => setShowCreateModal(true)}
              className="text-sm text-primary hover:underline font-medium"
            >
              + Create a new role
            </button>
          )}
        </div>
      )}

      {!loading && !error && filteredRoles.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {filteredRoles.map((role, idx) => (
            <JobRoleCard
              key={role.id}
              role={role}
              index={idx}
              onEdit={openEditModal}
              onDeactivate={handleDeactivate}
            />
          ))}
        </div>
      )}

      <AnimatePresence>
        {showCreateModal && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4"
            onClick={() => setShowCreateModal(false)}
          >
            <motion.div
              initial={{ scale: 0.95, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.95, opacity: 0 }}
              className="glass-card rounded-3xl p-8 w-full max-w-lg"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="flex items-center justify-between mb-6">
                <h2 className="text-2xl font-bold">Create New Role</h2>
                <button
                  onClick={() => setShowCreateModal(false)}
                  className="p-2 rounded-lg hover:bg-white/10 transition-colors"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>

              <div className="space-y-4">
                <div>
                  <label className="text-xs font-bold text-muted-foreground uppercase tracking-wider mb-2 block">
                    Role Title *
                  </label>
                  <input
                    type="text"
                    placeholder="e.g. Senior Frontend Engineer"
                    value={createForm.title}
                    onChange={(e) =>
                      setCreateForm({ ...createForm, title: e.target.value })
                    }
                    className="w-full bg-white/5 border border-border rounded-xl px-4 py-3 focus:outline-none focus:ring-2 focus:ring-primary/50 transition-all"
                    autoFocus
                  />
                </div>
                <div>
                  <label className="text-xs font-bold text-muted-foreground uppercase tracking-wider mb-2 block">
                    Description
                  </label>
                  <textarea
                    placeholder="Brief description of the role..."
                    value={createForm.description}
                    onChange={(e) =>
                      setCreateForm({
                        ...createForm,
                        description: e.target.value,
                      })
                    }
                    rows={3}
                    className="w-full bg-white/5 border border-border rounded-xl px-4 py-3 focus:outline-none focus:ring-2 focus:ring-primary/50 transition-all resize-none"
                  />
                </div>
              </div>

              <button
                onClick={handleCreateRole}
                disabled={!createForm.title.trim() || creating}
                className="w-full bg-primary text-primary-foreground font-bold py-3 rounded-xl mt-6 shadow-[0_0_20px_rgba(16,185,129,0.3)] hover:shadow-[0_0_30px_rgba(16,185,129,0.5)] transition-all disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
              >
                {creating && <Loader2 className="w-4 h-4 animate-spin" />}
                {creating ? "Creating..." : "Create Role"}
              </button>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      <AnimatePresence>
        {editingRole && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4"
            onClick={() => setEditingRole(null)}
          >
            <motion.div
              initial={{ scale: 0.95, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.95, opacity: 0 }}
              className="glass-card rounded-3xl p-8 w-full max-w-lg"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="flex items-center justify-between mb-6">
                <h2 className="text-2xl font-bold">Edit Role</h2>
                <button
                  onClick={() => setEditingRole(null)}
                  className="p-2 rounded-lg hover:bg-white/10 transition-colors"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>

              <div className="space-y-4">
                <div>
                  <label className="text-xs font-bold text-muted-foreground uppercase tracking-wider mb-2 block">
                    Role Title
                  </label>
                  <input
                    type="text"
                    value={editForm.title ?? ""}
                    onChange={(e) =>
                      setEditForm((prev) => ({
                        ...prev,
                        title: e.target.value,
                      }))
                    }
                    className="w-full bg-white/5 border border-border rounded-xl px-4 py-3 focus:outline-none focus:ring-2 focus:ring-primary/50 transition-all"
                  />
                </div>
                <div>
                  <label className="text-xs font-bold text-muted-foreground uppercase tracking-wider mb-2 block">
                    Description
                  </label>
                  <textarea
                    value={editForm.description ?? ""}
                    onChange={(e) =>
                      setEditForm((prev) => ({
                        ...prev,
                        description: e.target.value,
                      }))
                    }
                    rows={3}
                    className="w-full bg-white/5 border border-border rounded-xl px-4 py-3 focus:outline-none focus:ring-2 focus:ring-primary/50 transition-all resize-none"
                  />
                </div>
              </div>

              <button
                onClick={handleSaveEdit}
                disabled={!editForm.title?.trim() || savingEdit}
                className="w-full bg-primary text-primary-foreground font-bold py-3 rounded-xl mt-6 transition-all disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
              >
                {savingEdit && <Loader2 className="w-4 h-4 animate-spin" />}
                {savingEdit ? "Saving..." : "Save Changes"}
              </button>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};
