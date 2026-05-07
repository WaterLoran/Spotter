import api from "./api";

function rq(path) {
  const p = String(path).replace(/\/+$/, "");
  return p.startsWith("/") ? p : `/${p}`;
}

export const listRedisSessions = () => api.get(rq("/redis-query/sessions"));
export const createRedisSession = (payload) => api.post(rq("/redis-query/sessions"), payload);
export const updateRedisSession = (id, payload) => api.put(rq(`/redis-query/sessions/${id}`), payload);
export const deleteRedisSession = (id) => api.delete(rq(`/redis-query/sessions/${id}`));
export const testRedisSession = (payload) => api.post(rq("/redis-query/sessions/test"), payload);

export const listRedisTasks = () => api.get(rq("/redis-query/tasks"));
export const createRedisTask = (payload) => api.post(rq("/redis-query/tasks"), payload);
export const updateRedisTask = (id, payload) => api.put(rq(`/redis-query/tasks/${id}`), payload);
export const deleteRedisTask = (id) => api.delete(rq(`/redis-query/tasks/${id}`));
export const orderRedisTasks = (order) => api.put(rq("/redis-query/tasks/order"), { order });
export const refreshRedisTask = (id) => api.post(rq(`/redis-query/tasks/${id}/refresh`));
export const markRedisTaskSeen = (id) => api.post(rq(`/redis-query/tasks/${id}/seen`));
export const getRedisTaskHistory = (id, params) => api.get(rq(`/redis-query/tasks/${id}/history`), { params });
export const clearRedisTaskHistory = (id) => api.delete(rq(`/redis-query/tasks/${id}/history`));
