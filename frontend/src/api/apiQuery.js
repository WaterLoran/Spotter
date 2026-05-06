import api from "./api";

/** 避免请求路径末尾带 / 时部分环境下出现 405 */
function aq(path) {
  const p = String(path).replace(/\/+$/, "");
  return p.startsWith("/") ? p : `/${p}`;
}

export const listApiTasks = () => api.get(aq("/api-query/tasks"));
export const createApiTask = (payload) => api.post(aq("/api-query/tasks"), payload);
export const updateApiTask = (id, payload) => api.put(aq(`/api-query/tasks/${id}`), payload);
export const deleteApiTask = (id) => api.delete(aq(`/api-query/tasks/${id}`));
export const executeApiTask = (id) =>
  api.post(aq(`/api-query/tasks/${id}/execute`), {}, { timeout: 120000 });
export const getApiTaskHistory = (id) => api.get(aq(`/api-query/tasks/${id}/history`));
export const deleteApiTaskHistory = (id, hid) => api.delete(aq(`/api-query/tasks/${id}/history/${hid}`));

export const listHeaderSnippets = () => api.get(aq("/api-query/headers"));
export const createHeaderSnippet = (payload) => api.post(aq("/api-query/headers"), payload);
export const updateHeaderSnippet = (id, payload) => api.put(aq(`/api-query/headers/${id}`), payload);
export const deleteHeaderSnippet = (id) => api.delete(aq(`/api-query/headers/${id}`));
export const previewHeaderSnippet = (id) =>
  api.post(aq(`/api-query/headers/${id}/preview`), {}, { timeout: 60000 });
