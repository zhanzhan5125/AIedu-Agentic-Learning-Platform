<template>
  <div class="course-nav">
    <div class="course-title">{{ courseTitle }}</div>
    <el-menu :default-active="$route.path" router background-color="white" text-color="black"
             active-text-color="#2196f3" mode="horizontal" :ellipsis="true" class="course-menu">
      <el-menu-item index="/course">首页</el-menu-item>
      <el-menu-item index="/assignment">作业</el-menu-item>
      <el-menu-item index="/course_insights">学情洞察</el-menu-item>
      <el-menu-item index="/agent_studio">智能体工作台</el-menu-item>
      <el-menu-item index="/chatpage" disabled>考试</el-menu-item>
      <el-menu-item index="/course_resources">资料</el-menu-item>
      <el-menu-item index="/course_messages"><MessageUnreadBadge :offering-id="offeringId" /></el-menu-item>
      <el-menu-item index="/manage_stu">管理</el-menu-item>
    </el-menu>
  </div>
</template>

<script>
import MessageUnreadBadge from '@/components/MessageUnreadBadge.vue'
export default {
  components: { MessageUnreadBadge },
  computed: {
    course() { return this.$store.getters.getCourse || {} },
    courseTitle() { return this.course.title || this.course.tittle || '课程' },
    offeringId() { return this.course.offeringId || this.course.id || this.course.courseCode }
  }
}
</script>

<style scoped>
.course-nav { width: 100%; display: flex; align-items: stretch; border-bottom: 1px solid #dcdfe6; background: white; }
.course-title { display: flex; align-items: center; flex-shrink: 0; padding: 0 24px 0 70px; font-size: 18px; color: #2196f3; }
.course-menu { flex: 1; display: flex; justify-content: flex-end; border-bottom: none; padding-right: 50px; }
</style>
