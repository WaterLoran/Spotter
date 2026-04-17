<template>
  <div class="search-box">
    <el-input v-model="model" placeholder="关键词，分号分隔" @keyup.enter="emitSearch" />
    <el-button type="primary" @click="emitSearch">搜索</el-button>
    <el-button @click="clear">清空</el-button>
  </div>
</template>

<script setup>
import { ref, watch } from "vue";

const props = defineProps({ value: { type: String, default: "" } });
const emit = defineEmits(["search", "update:value"]);

const model = ref(props.value);
watch(
  () => props.value,
  (v) => (model.value = v)
);

function emitSearch() {
  emit("update:value", model.value);
  emit("search", model.value);
}

function clear() {
  model.value = "";
  emitSearch();
}
</script>

<style scoped>
.search-box {
  display: flex;
  gap: 8px;
}
</style>

