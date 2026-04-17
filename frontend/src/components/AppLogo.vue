<template>
  <div class="app-logo-wrap">
    <img :src="src" alt="Spotter" class="app-logo-img" />
    <span v-if="$slots.default" class="app-logo-text">
      <slot />
    </span>
  </div>
</template>

<script setup>
defineProps({
  src: { type: String, default: "/logo.png" }
});
</script>

<style scoped>
.app-logo-wrap {
  display: inline-flex;
  align-items: center;
  gap: 10px;
}
.app-logo-img {
  height: 30px;
  width: auto;
  display: block;
  object-fit: contain;
}
.app-logo-text {
  font-size: 1.5em;
  font-weight: 600;
  line-height: 1.2;
  margin: 0;
}
</style>
