import { defineStore } from "pinia";
import {
  createApiTask,
  createHeaderSnippet,
  deleteApiTask,
  deleteApiTaskHistory,
  deleteHeaderSnippet,
  executeApiTask,
  getApiTaskHistory,
  listApiTasks,
  listHeaderSnippets,
  previewHeaderSnippet,
  updateApiTask,
  updateHeaderSnippet
} from "../api/apiQuery";

/** @param {unknown} responseData */
export function extractTableRows(responseData) {
  if (!responseData) return [];
  if (
    Array.isArray(responseData) &&
    responseData.length &&
    responseData.every((x) => x && typeof x === "object" && !Array.isArray(x))
  ) {
    return responseData.map((row) => ({ ...row }));
  }
  if (typeof responseData === "object" && !Array.isArray(responseData)) {
    for (const v of Object.values(responseData)) {
      if (
        Array.isArray(v) &&
        v.length &&
        v.every((x) => x && typeof x === "object" && !Array.isArray(x))
      ) {
        return v.map((row) => ({ ...row }));
      }
    }
  }
  return [];
}

export const useApiQueryStore = defineStore("apiQueryStore", {
  state: () => ({
    currentTasks: [],
    taskResults: {},
    headerSnippets: []
  }),
  actions: {
    async loadHeaderSnippets() {
      const res = await listHeaderSnippets();
      this.headerSnippets = res.data || [];
    },
    async addHeaderSnippet(payload) {
      const res = await createHeaderSnippet(payload);
      await this.loadHeaderSnippets();
      return res;
    },
    async saveHeaderSnippet(id, payload) {
      const res = await updateHeaderSnippet(id, payload);
      await this.loadHeaderSnippets();
      return res;
    },
    async removeHeaderSnippet(id) {
      await deleteHeaderSnippet(id);
      await this.loadHeaderSnippets();
    },
    async previewHeader(id) {
      return previewHeaderSnippet(id);
    },
    async loadTasks() {
      const res = await listApiTasks();
      const list = res.data || [];
      this.currentTasks = list.map((t) => ({
        ...t,
        query_params: Array.isArray(t.query_params) ? t.query_params : []
      }));
    },
    async addTask(payload) {
      const res = await createApiTask(payload);
      await this.loadTasks();
      return res;
    },
    async editTask(id, payload) {
      const res = await updateApiTask(id, payload);
      await this.loadTasks();
      return res;
    },
    async patchTaskPolling(id, partial) {
      const res = await updateApiTask(id, partial);
      if (res?.success === false) return res;
      const q = this.currentTasks.find((x) => Number(x.id) === Number(id));
      if (q) {
        if ("is_active" in partial) q.is_active = partial.is_active;
        if ("polling_interval" in partial) q.polling_interval = partial.polling_interval;
      }
      return res;
    },
    async removeTask(id) {
      await deleteApiTask(id);
      await this.loadTasks();
    },
    _resultKey(id) {
      return String(id);
    },
    _isViewingNonLatest(key) {
      const b = this.taskResults[key];
      if (!b?.history?.length || b.currentHistoryId == null) return false;
      const latestId = b.history[0].id;
      return b.currentHistoryId !== latestId;
    },
    /**
     * @param {object} [opts]
     * @param {boolean} [opts.respectHistorySelection=true]
     */
    async executeTaskOnce(id, opts = {}) {
      const respect = opts.respectHistorySelection !== false;
      const key = this._resultKey(id);
      const viewingOld = respect && this._isViewingNonLatest(key);

      const res = await executeApiTask(id);
      if (!this.taskResults[key]) {
        this.taskResults[key] = { history: [], currentHistoryId: null, data: [] };
      }
      if (!res.success) {
        return res;
      }

      if (!viewingOld) {
        if (res.data) {
          const tableFromResponse = extractTableRows(res.data.response_data);
          const fallbackRows = Array.isArray(res.data.rows)
            ? res.data.rows.map((row) => ({ ...row }))
            : [];
          this.taskResults[key].data =
            tableFromResponse.length > 0 ? tableFromResponse : fallbackRows;
          if (res.data.history_id != null) {
            this.taskResults[key].currentHistoryId = res.data.history_id;
          }
        }
        await this.loadTaskHistory(id);
        return res;
      }

      const noNewHistory = res.data?.history_appended === false;
      if (noNewHistory) {
        return res;
      }

      await this.loadTaskHistory(id, { preserveSelection: true });
      return res;
    },
    async loadTaskHistory(id, opts = {}) {
      const { preserveSelection = false } = opts;
      const key = this._resultKey(id);
      const res = await getApiTaskHistory(id);
      const list = res.data || [];
      const history = list.map((h) => ({ ...h }));
      const prev = this.taskResults[key];
      const prevId = prev?.currentHistoryId;

      let currentHistoryId = null;
      let data = [];
      if (preserveSelection && prevId != null && history.some((h) => h.id === prevId)) {
        currentHistoryId = prevId;
        const item = history.find((h) => h.id === prevId);
        data = extractTableRows(item?.response_data);
      } else if (history.length > 0) {
        const latest = history[0];
        currentHistoryId = latest.id;
        data = extractTableRows(latest.response_data);
      }
      this.taskResults[key] = { history, currentHistoryId, data };
    },
    setCurrentHistory(taskId, historyId) {
      const key = this._resultKey(taskId);
      const target = this.taskResults[key];
      if (!target) return;
      const item = (target.history || []).find((h) => h.id === historyId);
      const data = extractTableRows(item?.response_data);
      this.taskResults[key] = {
        ...target,
        currentHistoryId: historyId,
        data
      };
    },
    async deleteHistory(taskId, historyId) {
      await deleteApiTaskHistory(taskId, historyId);
      await this.loadTaskHistory(taskId);
    }
  }
});
