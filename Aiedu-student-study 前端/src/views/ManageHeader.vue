<template>
  <div class="layout-container" :class="{ 'teacher-course-shell': isTeacherCourse }">
    <!-- Header 部分 -->
    <HeaderComponent />
    <!-- Sidebar 和主内容部分 -->
    <div class="main-container" :class="{ 'teacher-course-layout': isTeacherCourse }">
      <TeacherCourseAside v-if="isTeacherCourse" />
      <!-- 主内容区域 -->
      <el-main :class="{ 'teacher-course-content': isTeacherCourse }" style="padding: 0;">
        <router-view/>
      </el-main>
    </div>
  </div>
</template>

<script>
import HeaderComponent from '../components/Header.vue';
import TeacherCourseAside from '../components/TeacherCourseAside.vue';

export default {
  components: {
    HeaderComponent,
    TeacherCourseAside,
  },
  computed: {
    isTeacherCourse() {
      const user = this.$store.getters.getUser || {}
      return (user.role || user.identity) === 'teacher' && Boolean(this.$route.meta && this.$route.meta.teacherCourse)
    }
  },
  data() {
    return {
    };
  },
};
</script>

<style>
.layout-container {
  display: flex;
  flex-direction: column;
}
.main-container {
  display: flex;
  flex: 1;
}
.teacher-course-layout { min-height: calc(100vh - 80px); background: #f6f8fb; }
.teacher-course-shell { height: auto; min-height: 100vh; }
.teacher-course-layout { align-items: stretch; }
.teacher-course-content { position: relative; z-index: 1; min-width: 0; overflow-x: hidden; }
/* Legacy pages carried their own horizontal course menu. The course shell now
   owns navigation, so suppress those duplicate bars until the pages are fully
   decomposed into content-only views. */
.teacher-course-content > div > .wrapper:first-child,
.teacher-course-content > div > .header-container:first-child,
.teacher-course-content > .page-shell > .course-nav:first-child {
  display: none !important;
}
.teacher-course-content > .page-shell { padding-top: 32px !important; }
</style>
