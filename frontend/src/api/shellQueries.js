import api from "./api";

export const listShellQueriesApi = () => api.get("/shell/queries");
export const createShellQueryApi = (payload) => api.post("/shell/queries", payload);
export const updateShellQueryApi = (id, payload) => api.put(`/shell/queries/${id}`, payload);
export const deleteShellQueryApi = (id) => api.delete(`/shell/queries/${id}`);
export const executeShellQueryApi = (id) => api.post(`/shell/queries/${id}/execute`);
export const getShellQueryHistoryApi = (id) => api.get(`/shell/queries/${id}/history`);
export const deleteShellQueryHistoryApi = (id, hid) => api.delete(`/shell/queries/${id}/history/${hid}`);
export const shellPresetsApi = () => api.get("/shell/presets");

