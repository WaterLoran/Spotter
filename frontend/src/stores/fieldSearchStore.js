import { defineStore } from "pinia";

export const useFieldSearchStore = defineStore("fieldSearchStore", {
  state: () => ({
    currentTabs: []
  }),
  actions: {
    openTab(tab) {
      if (!this.currentTabs.find((t) => t.id === tab.id)) {
        this.currentTabs.push(tab);
      }
    },
    closeTab(id) {
      this.currentTabs = this.currentTabs.filter((t) => t.id !== id);
    },
    updateTabData(id, patch) {
      const idx = this.currentTabs.findIndex((t) => t.id === id);
      if (idx >= 0) this.currentTabs[idx] = { ...this.currentTabs[idx], ...patch };
    },
    updateTabField(id, key, value) {
      const idx = this.currentTabs.findIndex((t) => t.id === id);
      if (idx >= 0) this.currentTabs[idx][key] = value;
    },
    moveTabLeft(id) {
      const idx = this.currentTabs.findIndex((t) => t.id === id);
      if (idx > 0) {
        const [item] = this.currentTabs.splice(idx, 1);
        this.currentTabs.splice(idx - 1, 0, item);
      }
    },
    moveTabRight(id) {
      const idx = this.currentTabs.findIndex((t) => t.id === id);
      if (idx >= 0 && idx < this.currentTabs.length - 1) {
        const [item] = this.currentTabs.splice(idx, 1);
        this.currentTabs.splice(idx + 1, 0, item);
      }
    }
  }
});

