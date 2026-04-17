import api from "./api";

export const listSqlQueries = () => api.get("/sql/queries");
export const createSqlQuery = (payload) => api.post("/sql/queries", payload);
export const updateSqlQuery = (id, payload) => api.put(`/sql/queries/${id}`, payload);
export const deleteSqlQuery = (id) => api.delete(`/sql/queries/${id}`);
export const executeSqlQuery = (id) => api.post(`/sql/queries/${id}/execute`);
export const getSqlQueryHistory = (id) => api.get(`/sql/queries/${id}/history`);
export const deleteSqlQueryHistory = (queryId, historyId) =>
  api.post(`/sql/queries/${queryId}/history/${historyId}/delete`);

