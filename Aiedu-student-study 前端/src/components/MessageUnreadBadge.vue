<template>
  <span class="message-menu-label">
    <span>消息</span>
    <el-badge v-if="unreadCount > 0" :value="badgeValue" class="message-unread-badge" />
  </span>
</template>

<script>
export default {
  name: 'MessageUnreadBadge',
  props: {
    offeringId: { type: [Number, String], default: null }
  },
  computed: {
    unreadCount() { return this.$store.getters.getUnreadTotal(this.offeringId) },
    badgeValue() { return this.unreadCount > 99 ? '99+' : this.unreadCount }
  },
  watch: {
    offeringId() { this.$store.dispatch('loadUnread', this.offeringId || null) }
  },
  created() {
    this.$store.dispatch('ensureUnreadSync', this.offeringId || null)
  }
}
</script>

<style scoped>
.message-menu-label { display: inline-flex; align-items: center; gap: 10px; }
.message-unread-badge { line-height: 1; }
/deep/ .message-unread-badge .el-badge__content { border: 0; }
</style>
