<template>
  <el-aside class="teacher-course-aside" width="250px">
    <div class="course-info">
      <div class="course-cover"><img src="../views/img/封面.jpg" alt="课程封面"></div>
      <div class="course-name">{{ courseTitle }}</div>
    </div>
    <div class="divider"><img src="../views/img/img2.png" height="1" width="200" alt=""></div>
    <el-menu :default-active="activePath" router background-color="white" text-color="black"
             active-text-color="#2196f3" mode="vertical" class="course-menu">
      <el-menu-item index="/course"><el-icon name="house"></el-icon>课程首页</el-menu-item>
      <el-menu-item index="/assignment"><el-icon name="notebook-2"></el-icon>作业</el-menu-item>
      <el-menu-item index="/course_insights"><el-icon name="data-analysis"></el-icon>学情洞察</el-menu-item>
      <el-menu-item index="/agent_studio"><el-icon name="cpu"></el-icon>智能体工作台</el-menu-item>
      <el-menu-item index="/course_resources"><el-icon name="reading"></el-icon>资料</el-menu-item>
      <el-menu-item index="/course_messages">
        <el-icon name="message"></el-icon>
        <MessageUnreadBadge :offering-id="offeringId" />
      </el-menu-item>
      <el-menu-item index="/manage_stu"><el-icon name="user"></el-icon>课程管理</el-menu-item>
    </el-menu>
  </el-aside>
</template>

<script>
import MessageUnreadBadge from '@/components/MessageUnreadBadge.vue'

const assignmentChildren = ['/assignment_item', '/checkassignment', '/assignment_detail', '/no_submitted', '/teacher_mark', '/teacher_create_assignment', '/llmcheck']

export default {
  components: { MessageUnreadBadge },
  computed: {
    course() { return this.$store.getters.getCourse || {} },
    courseTitle() { return this.course.title || this.course.tittle || '课程' },
    offeringId() { return this.course.offeringId || this.course.id || this.course.courseCode },
    activePath() {
      if (assignmentChildren.includes(this.$route.path)) return '/assignment'
      if (this.$route.path === '/manage_ass') return '/manage_stu'
      return this.$route.path
    }
  }
}
</script>

<style scoped>
.teacher-course-aside {
  position: relative;
  z-index: 2;
  align-self: stretch;
  flex: 0 0 250px;
  min-height: calc(100vh - 80px);
  overflow: visible;
  background: #fff;
  border-right: 1px solid #e5e9f0;
  box-shadow: 7px 0 14px -8px rgba(32, 56, 85, .42);
}
.course-info { display: flex; flex-direction: column; align-items: center; padding: 20px; }
.course-cover { width: 200px; height: 100px; overflow: hidden; }
.course-cover img { width: 100%; height: 100%; object-fit: cover; }
.course-name { margin-top: 10px; font-size: 20px; font-weight: 700; text-align: center; }
.divider { display: flex; justify-content: center; }
.course-menu { margin-top: 30px; border-right: none; }
.course-menu .el-menu-item { font-size: 17px; text-align: left; }
.course-menu .el-icon { margin-right: 8px; }
</style>
