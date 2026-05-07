import { defineStore } from "pinia";
import {
  clearRedisTaskHistory,
  getRedisTaskHistory,
  listRedisSessions,
  listRedisTasks,
  markRedisTaskSeen
} from "../api/redisQuery";

export const useRedisQueryStore = defineStore("redisQueryStore", {
  state: () => ({
    sessions: [],
    tasks: [],
    /** @type {Record<string, Array<{id:number,value:string,value_type:string,recorded_at:string}>>} */
    taskHistory: {},
    eventSource: null,
    reconnectTimer: null
  }),
  actions: {
    applySsePayload(d) {
      if (!d || d.type !== "task_update") return;
      const tid = Number(d.task_id);
      const i = this.tasks.findIndex((t) => Number(t.id) === tid);
      if (i >= 0) {
        const cur = { ...this.tasks[i] };
        if ("latest_value" in d) cur.latest_value = d.latest_value;
        if ("latest_value_type" in d) cur.latest_value_type = d.latest_value_type;
        if ("last_changed_at" in d) cur.last_changed_at = d.last_changed_at;
        if ("change_count_since_seen" in d) cur.change_count_since_seen = d.change_count_since_seen;
        this.tasks.splice(i, 1, cur);
      }
      const h = d.history;
      if (h && h.id != null) {
        const key = String(tid);
        if (!this.taskHistory[key]) this.taskHistory[key] = [];
        const arr = this.taskHistory[key];
        if (!arr.some((x) => x.id === h.id)) {
          arr.unshift({
            id: h.id,
            value: h.value,
            value_type: h.value_type,
            recorded_at: h.recorded_at
          });
        }
      }
    },

    disconnectEventSource() {
      if (this.reconnectTimer != null) {
        clearTimeout(this.reconnectTimer);
        this.reconnectTimer = null;
      }
      if (this.eventSource) {
        try {
          this.eventSource.close();
        } catch {
          /* ignore */
        }
        this.eventSource = null;
      }
    },

    connectEventSource() {
      this.disconnectEventSource();
      const systemId = localStorage.getItem("fastlog_current_system_id") || "1";
      const url = `/api/redis-query/events?system_id=${encodeURIComponent(systemId)}`;
      const es = new EventSource(url);
      this.eventSource = es;
      es.onmessage = (ev) => {
        try {
          const d = JSON.parse(ev.data);
          this.applySsePayload(d);
        } catch {
          /* ignore */
        }
      };
      es.onerror = () => {
        if (this.eventSource !== es) return;
        try {
          es.close();
        } catch {
          /* ignore */
        }
        this.eventSource = null;
        if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
        this.reconnectTimer = setTimeout(() => {
          this.connectEventSource();
        }, 5000);
      };
    },

    async loadSessions() {
      const res = await listRedisSessions();
      this.sessions = res.data || [];
    },

    async loadTasks() {
      const res = await listRedisTasks();
      this.tasks = (res.data || []).map((t) => ({ ...t }));
    },

    async loadTaskHistory(taskId, { limit } = { limit: 200 }) {
      const res = await getRedisTaskHistory(taskId, { limit });
      const list = res.data || [];
      this.taskHistory[String(taskId)] = list.map((x) => ({ ...x }));
    },

    async clearTaskHistory(taskId) {
      await clearRedisTaskHistory(taskId);
      this.taskHistory[String(taskId)] = [];
    },

    async markSeen(taskId) {
      const res = await markRedisTaskSeen(taskId);
      const d = res.data;
      if (d && d.id != null) {
        const i = this.tasks.findIndex((t) => Number(t.id) === Number(d.id));
        if (i >= 0) this.tasks.splice(i, 1, { ...this.tasks[i], ...d });
      }
    }
  }
});
