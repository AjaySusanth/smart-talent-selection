import axios from "axios";
import type { JobRole, JobRoleUpdate } from "../types";

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL || "http://localhost:8000/api/v1";
const API_KEY = import.meta.env.VITE_API_KEY || "";
const ROOT_BASE_URL = API_BASE_URL.replace(/\/api\/v1\/?$/, "");

export const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    "Content-Type": "application/json",
    "x-api-key": API_KEY,
  },
});

// Response interceptor for global error handling
api.interceptors.response.use(
  (response) => response,
  (error) => {
    const status = error.response?.status;
    const detail = error.response?.data?.detail;

    if (status === 401 || status === 403) {
      console.error("Auth Error: Invalid or missing API key.");
    } else if (status === 404) {
      console.warn("Not Found:", detail || error.config?.url);
    } else if (status && status >= 500) {
      console.error(
        "Server Error:",
        detail || "An internal server error occurred.",
      );
    } else {
      console.error("API Error:", error.message);
    }

    return Promise.reject(error);
  },
);

// Helper method to get candidate counts for dashboard
export const getCandidateCounts = () => api.get("/candidates/count");

// Helper method to update a job role
export const updateJobRole = (id: string, payload: JobRoleUpdate) =>
  api.patch<JobRole>(`/job-roles/${id}`, payload);

// Helper method to deactivate a job role
export const deactivateJobRole = (id: string) => api.delete(`/job-roles/${id}`);

// Helper method to get signed URL for resume download
export const getResumeFileUrl = (uploadId: string) =>
  api.get(`/resumes/${uploadId}/file`);

export const listRoleResumes = (jobRoleId: string) =>
  api.get("/resumes", { params: { job_role_id: jobRoleId } });

export const uploadResumes = (jobRoleId: string, files: File[]) => {
  const formData = new FormData();
  formData.append("job_role_id", jobRoleId);
  files.forEach((file) => formData.append("files", file));
  return api.post("/resumes/upload", formData, {
    headers: {
      "Content-Type": "multipart/form-data",
      "x-api-key": API_KEY,
    },
  });
};

export const getResumeStatus = (uploadId: string) =>
  api.get(`/resumes/status/${uploadId}`);

export const getReadiness = () =>
  axios.get(`${ROOT_BASE_URL}/health/ready`, {
    headers: {
      "x-api-key": API_KEY,
    },
  });
