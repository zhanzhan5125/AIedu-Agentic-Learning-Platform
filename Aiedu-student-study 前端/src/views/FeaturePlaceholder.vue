<template>
  <div class="feature-page">
    <el-empty :description="`${title}正在建设中`">
      <el-tag type="warning">功能已进入迁移路线，当前不会展示假数据</el-tag>
    </el-empty>
  </div>
</template>

<script>
export default {
  computed: {
    title() { return this.$route.meta.title || this.$route.name || '该功能' }
  }
}
</script>

<style scoped>
.feature-page { min-height: 60vh; display: flex; align-items: center; justify-content: center; }
</style>
