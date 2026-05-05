import api from "./api";

/** Normalize GET /sql/sessions `data`: array, or legacy single session object. */
export function normalizeSqlSessionsData(data) {
  if (data == null) return [];
  if (Array.isArray(data)) return data;
  if (typeof data === "object" && "id" in data) return [data];
  return [];
}

/** @param {"mysql"|"pgsql"|"oracle"|""} [dbType] */
export const listSqlSessions = (dbType) =>
  api.get("/sql/sessions", { params: dbType ? { db_type: dbType } : {} });

export const createSqlSession = (payload) => api.post("/sql/sessions", payload);

export const updateSqlSession = (id, payload) => api.put(`/sql/sessions/${id}`, payload);

export const deleteSqlSession = (id) => api.delete(`/sql/sessions/${id}`);

export const testSqlSession = (payload) => api.post("/sql/sessions/test", payload);
