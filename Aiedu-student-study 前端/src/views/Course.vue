<template>
  <div>
    <div class="wrapper course-header">
      <p class="course-name">{{ courseTitle }}</p>
      <el-menu
          :default-active="'/course'"
          router
          background-color="white"
          text-color="black"
          active-text-color="#2196f3"
          class="el-menu-demo"
          mode="horizontal"
      >
        <el-menu-item index="/course">首页</el-menu-item>
        <el-menu-item index="/assignment">作业</el-menu-item>
        <el-menu-item index="/course_insights">学情洞察</el-menu-item>
        <el-menu-item index="/agent_studio">智能体工作台</el-menu-item>
        <el-menu-item index="/chatpage" :disabled="true">考试</el-menu-item>
        <el-menu-item index="/course_resources">资料</el-menu-item>
        <el-menu-item index="/course_messages"><MessageUnreadBadge :offering-id="course.offeringId || course.id || course.courseCode" /></el-menu-item>
        <el-menu-item index="/manage_stu">管理</el-menu-item>
      </el-menu>
    </div>

    <el-main class="course-main">
      <el-card shadow="never" class="overview-card">
        <div slot="header" class="card-header">
          <span>课程概览</span>
          <el-button type="text" @click="$router.push('/home')">返回课程列表</el-button>
        </div>
        <el-descriptions :column="1" border>
          <el-descriptions-item label="课程名称">{{ courseTitle }}</el-descriptions-item>
          <el-descriptions-item label="课程编号">{{ course.cno || course.courseNumber || '暂无' }}</el-descriptions-item>
          <el-descriptions-item label="授课教师">{{ course.teacher || (user && user.name) || '暂无' }}</el-descriptions-item>
          <el-descriptions-item label="教学班">{{ course.sectionName || ('教学班' + (course.sectionCode || '01')) }}（{{ course.sectionCode || '01' }}）</el-descriptions-item>
          <el-descriptions-item label="学年学期">{{ schoolTerm }}</el-descriptions-item>
        </el-descriptions>
      </el-card>

      <el-alert
          class="feature-tip"
          title="请通过上方导航进入作业或课程管理。"
          type="info"
          :closable="false"
          show-icon
      />
    </el-main>
  </div>
</template>

<script>
export default {
  data() {
    return {
      course: {},
      user: null
    };
  },
  computed: {
    courseTitle() {
      return this.course.title || this.course.tittle || '课程首页';
    },
    schoolTerm() {
      if (!this.course.year) {
        return '暂无';
      }
      const term = this.course.term ? `（第 ${this.course.term} 学期）` : '';
      return `${this.course.year}-${Number(this.course.year) + 1}${term}`;
    }
  },
  created() {
    this.course = this.$store.getters.getCourse || {};
    this.user = this.$store.getters.getUser;

    if (!(this.course.id || this.course.offeringId || this.course.courseCode)) {
      this.$message.warning('请先从教师主页选择一门课程');
      this.$router.replace('/home');
    }
  }
};
</script>

<style scoped>
.course-header {
  width: 100%;
  display: flex;
  padding-top: 0;
  border-bottom: 1px solid #ccc;
}

.course-name {
  font-size: larger;
  color: #2196f3;
  padding: 17px 0 17px 70px;
  margin: 0;
}

.el-menu-demo {
  flex-grow: 1;
  display: flex;
  justify-content: flex-end;
  border-bottom: none;
  padding-right: 50px;
}

.course-main {
  min-height: 85vh;
  background: #f6f8fb;
  padding: 40px 70px;
}

.overview-card {
  max-width: 900px;
  margin: 0 auto;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 20px;
  font-weight: bold;
}

.feature-tip {
  max-width: 900px;
  margin: 20px auto 0;
}
</style>
