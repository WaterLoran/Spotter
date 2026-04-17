import { defineStore } from "pinia";
import { loadSqlSession, saveSqlSession, testSqlSession } from "../api/sqlSessions";

export const useSessionStore = defineStore("sessionStore", {
  state: () => ({
    currentSession: null,
    loading: false
  }),
  actions: {
    async loadSession() {
      this.loading = true;
      try {
        const res = await loadSqlSession();
        this.currentSession = res.data;
      } finally {
        this.loading = false;
      }
    },
    async saveSession(data) {
      const res = await saveSqlSession(data);
      await this.loadSession();
      return res;
    },
    async testConnection(payload) {
      return testSqlSession(payload || this.currentSession || {});
    }
  }
});

