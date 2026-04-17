import api from "./api";

export const loadSqlSession = () => api.get("/sql/sessions");
export const saveSqlSession = (payload) => api.post("/sql/sessions", payload);
export const testSqlSession = (payload) => api.post("/sql/sessions/test", payload);

