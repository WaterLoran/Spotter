import axios from "axios";

const api = axios.create({
  baseURL: "/api",
  timeout: 30000
});

api.interceptors.request.use((config) => {
  const systemId = localStorage.getItem("fastlog_current_system_id") || "1";
  config.headers["X-FastLog-System-Id"] = systemId;
  if (config.url?.includes("/logs")) {
    config.timeout = 120000;
  }
  return config;
});

api.interceptors.response.use(
  (response) => response.data,
  (error) => {
    const res = error.response;
    const data = res?.data;
    if (data && typeof data === "object") {
      const msg = data.error ?? data.message;
      if (typeof msg === "string" && msg.trim()) {
        return Promise.reject(new Error(msg.trim()));
      }
    }
    if (error.code === "ERR_NETWORK" || error.message === "Network Error") {
      return Promise.reject(
        new Error(
          "无法连到 Spotter 后端（浏览器报 Network Error）：请确认已启动 backend（例如 PORT=5001），并用 Vite 开发页访问以便 /api 代理到该端口；与数据库端口(如 33060)无关。"
        )
      );
    }
    if (res?.status) {
      const t = res.statusText || `HTTP ${res.status}`;
      return Promise.reject(new Error(t));
    }
    return Promise.reject(error);
  }
);

export const health = () => api.get("/health");
export const getConfig = () => api.get("/config");
export const updateConfig = (payload) => api.post("/config", payload);
export const applyConfig = (payload) => api.post("/config/apply", payload);
export const testConnection = (payload = {}) => api.post("/test-connection", payload);
export const reinitialize = () => api.post("/reinitialize");
export const reinitializeProgress = (taskId) => api.get(`/reinitialize/progress/${taskId}`);
export const cancelReinitialize = (taskId) => api.post(`/reinitialize/cancel/${taskId}`);

export const getLogs = (params) => api.get("/logs", { params });
export const deleteLog = (id) => api.delete(`/logs/${id}`);
export const deleteAllLogs = () => api.delete("/logs");
export const updateLogNotes = (id, notes) => api.put(`/logs/${id}/notes`, { notes });
export const bulkUpdateLogNotes = (payload) => api.put("/logs/notes", payload);
export const appendLogs = (payload) => api.post("/logs/append", payload);
export const appendLogsProgress = (taskId) => api.get(`/logs/append/progress/${taskId}`);
export const cancelAppendLogs = (taskId) => api.post(`/logs/append/cancel/${taskId}`);
export const dedupeLogsByContent = () => api.post("/logs/dedupe-by-content");

export const listSystems = () => api.get("/systems");
export const createSystem = (name) => api.post("/systems", { name });
export const renameSystem = (id, name) => api.put(`/systems/${id}`, { name });
export const deleteSystem = (id) => api.delete(`/systems/${id}`);

export const listSearchConfigs = () => api.get("/search-configs");
export const createSearchConfig = (payload) => api.post("/search-configs", payload);
export const updateSearchConfig = (id, payload) => api.put(`/search-configs/${id}`, payload);
export const deleteSearchConfig = (id) => api.delete(`/search-configs/${id}`);
export const executeSearchConfigs = () => api.post("/search-configs/execute");
export const executeSearchConfigsProgress = (taskId) => api.get(`/search-configs/execute/progress/${taskId}`);

export const listLogViews = () => api.get("/log-views");
export const createLogView = (payload) => api.post("/log-views", payload);
export const updateLogView = (id, payload) => api.put(`/log-views/${id}`, payload);
export const deleteLogView = (id) => api.delete(`/log-views/${id}`);

export const listTimelineNotes = (viewId) => api.get(`/log-views/${viewId}/timeline-notes`);
export const createTimelineNote = (viewId, payload) => api.post(`/log-views/${viewId}/timeline-notes`, payload);
export const updateTimelineNote = (id, payload) => api.put(`/log-views/timeline-notes/${id}`, payload);
export const deleteTimelineNote = (id) => api.delete(`/log-views/timeline-notes/${id}`);

export const listShellQueries = () => api.get("/shell/queries");
export const createShellQuery = (payload) => api.post("/shell/queries", payload);
export const updateShellQuery = (id, payload) => api.put(`/shell/queries/${id}`, payload);
export const deleteShellQuery = (id) => api.delete(`/shell/queries/${id}`);
export const executeShellQuery = (id) => api.post(`/shell/queries/${id}/execute`);
export const listShellQueryHistory = (id) => api.get(`/shell/queries/${id}/history`);
export const deleteShellQueryHistory = (id, hid) => api.delete(`/shell/queries/${id}/history/${hid}`);
export const listShellPresets = () => api.get("/shell/presets");

export const listBackgroundTasks = () => api.get("/background-tasks");

export default api;

