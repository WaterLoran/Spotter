import { defineStore } from "pinia";
import {
  createSqlQuery,
  deleteSqlQuery,
  deleteSqlQueryHistory,
  executeSqlQuery,
  getSqlQueryHistory,
  listSqlQueries,
  updateSqlQuery
} from "../api/sqlQueries";

export const useQueryStore = defineStore("queryStore", {
  state: () => ({
    currentQueries: [],
    queryResults: {}
  }),
  actions: {
    async loadQueries() {
      const res = await listSqlQueries();
      this.currentQueries = res.data || [];
    },
    async addQuery(payload) {
      const res = await createSqlQuery(payload);
      await this.loadQueries();
      return res;
    },
    async editQuery(id, payload) {
      const res = await updateSqlQuery(id, payload);
      await this.loadQueries();
      return res;
    },
    async patchQueryPolling(id, partial) {
      const res = await updateSqlQuery(id, partial);
      if (res?.success === false) return res;
      const q = this.currentQueries.find((x) => Number(x.id) === Number(id));
      if (q) {
        if ("is_active" in partial) q.is_active = partial.is_active;
        if ("polling_interval" in partial) q.polling_interval = partial.polling_interval;
      }
      return res;
    },
    async patchQuerySession(id, sessionId) {
      const res = await updateSqlQuery(id, { session_id: sessionId });
      if (res?.success === false) return res;
      const q = this.currentQueries.find((x) => Number(x.id) === Number(id));
      if (q) q.session_id = sessionId;
      return res;
    },
    async removeQuery(id) {
      await deleteSqlQuery(id);
      await this.loadQueries();
    },
    _resultKey(id) {
      return String(id);
    },
    _isViewingNonLatest(key) {
      const b = this.queryResults[key];
      if (!b?.history?.length || b.currentHistoryId == null) return false;
      const latestId = b.history[0].id;
      return b.currentHistoryId !== latestId;
    },
    /**
     * @param {object} [opts]
     * @param {boolean} [opts.respectHistorySelection=true] 为 false 时（如手动「执行一次」）始终跟最新结果；为 true 时若正在查看旧快照，相同结果不刷新、仅在有新历史行时更新左侧列表
     */
    async executeQueryOnce(id, opts = {}) {
      const respect = opts.respectHistorySelection !== false;
      const key = this._resultKey(id);
      const viewingOld = respect && this._isViewingNonLatest(key);

      const res = await executeSqlQuery(id);
      if (!this.queryResults[key]) {
        this.queryResults[key] = { history: [], currentHistoryId: null, data: [] };
      }
      if (!res.success) {
        return res;
      }

      if (!viewingOld) {
        if (res.data && Array.isArray(res.data.rows)) {
          this.queryResults[key].data = res.data.rows.map((row) => ({ ...row }));
          if (res.data.history_id != null) {
            this.queryResults[key].currentHistoryId = res.data.history_id;
          }
        }
        await this.loadQueryHistory(id);
        return res;
      }

      const noNewHistory = res.data?.history_appended === false;
      if (noNewHistory) {
        return res;
      }

      await this.loadQueryHistory(id, { preserveSelection: true });
      return res;
    },
    async loadQueryHistory(id, opts = {}) {
      const { preserveSelection = false } = opts;
      const key = this._resultKey(id);
      const res = await getSqlQueryHistory(id);
      const list = res.data || [];
      const history = list.map((h) => ({ ...h }));
      const prev = this.queryResults[key];
      const prevId = prev?.currentHistoryId;

      let currentHistoryId = null;
      let data = [];
      if (preserveSelection && prevId != null && history.some((h) => h.id === prevId)) {
        currentHistoryId = prevId;
        const item = history.find((h) => h.id === prevId);
        const rows = item?.result_data;
        data = Array.isArray(rows) ? rows.map((row) => ({ ...row })) : [];
      } else if (history.length > 0) {
        const latest = history[0];
        currentHistoryId = latest.id;
        const rows = latest.result_data;
        data = Array.isArray(rows) ? rows.map((row) => ({ ...row })) : [];
      }
      this.queryResults[key] = { history, currentHistoryId, data };
    },
    setCurrentHistory(queryId, historyId) {
      const key = this._resultKey(queryId);
      const target = this.queryResults[key];
      if (!target) return;
      const item = (target.history || []).find((h) => h.id === historyId);
      const rows = item?.result_data;
      const data = Array.isArray(rows) ? rows.map((row) => ({ ...row })) : [];
      this.queryResults[key] = {
        ...target,
        currentHistoryId: historyId,
        data
      };
    },
    async deleteHistory(queryId, historyId) {
      await deleteSqlQueryHistory(queryId, historyId);
      await this.loadQueryHistory(queryId);
    }
  }
});

