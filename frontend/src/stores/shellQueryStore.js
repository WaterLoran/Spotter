import { defineStore } from "pinia";
import {
  createShellQueryApi,
  deleteShellQueryApi,
  deleteShellQueryHistoryApi,
  executeShellQueryApi,
  getShellQueryHistoryApi,
  listShellQueriesApi,
  updateShellQueryApi
} from "../api/shellQueries";

export const useShellQueryStore = defineStore("shellQueryStore", {
  state: () => ({
    currentQueries: [],
    shellResults: {}
  }),
  actions: {
    async loadQueries() {
      const res = await listShellQueriesApi();
      this.currentQueries = res.data || [];
    },
    async addQuery(payload) {
      const res = await createShellQueryApi(payload);
      await this.loadQueries();
      return res;
    },
    async editQuery(id, payload) {
      await updateShellQueryApi(id, payload);
      await this.loadQueries();
    },
    async removeQuery(id) {
      await deleteShellQueryApi(id);
      await this.loadQueries();
    },
    async executeQueryOnce(id) {
      const res = await executeShellQueryApi(id);
      await this.loadQueryHistory(id);
      return res;
    },
    async loadQueryHistory(id) {
      const res = await getShellQueryHistoryApi(id);
      if (!this.shellResults[id]) {
        this.shellResults[id] = { history: [], currentHistoryId: null, fullOutput: "" };
      }
      this.shellResults[id].history = res.data || [];
      if (this.shellResults[id].history.length > 0) {
        this.shellResults[id].currentHistoryId = this.shellResults[id].history[0].id;
        this.shellResults[id].fullOutput = this.shellResults[id].history[0].full_output || "";
      }
    },
    setCurrentHistory(queryId, historyId) {
      const target = this.shellResults[queryId];
      if (!target) return;
      target.currentHistoryId = historyId;
      const item = (target.history || []).find((h) => h.id === historyId);
      target.fullOutput = item?.full_output || "";
    },
    async deleteHistory(queryId, historyId) {
      await deleteShellQueryHistoryApi(queryId, historyId);
      await this.loadQueryHistory(queryId);
    }
  }
});

