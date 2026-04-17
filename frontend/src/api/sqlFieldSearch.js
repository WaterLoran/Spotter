import api from "./api";

export const listFieldSearchTasks = () => api.get("/sql/field-search/tasks");
export const createFieldSearchTask = (payload) => api.post("/sql/field-search/tasks", payload);
export const getFieldSearchTask = (id) => api.get(`/sql/field-search/tasks/${id}`);
export const updateFieldSearchTask = (id, payload) => api.put(`/sql/field-search/tasks/${id}`, payload);
export const deleteFieldSearchTask = (id) => api.delete(`/sql/field-search/tasks/${id}`);
export const executeFieldSearch = (sessionId, payload) => api.post(`/sql/field-search/${sessionId}`, payload);
export const fieldSearchBackground = (jobId) => api.get(`/sql/field-search/background/${jobId}`);

