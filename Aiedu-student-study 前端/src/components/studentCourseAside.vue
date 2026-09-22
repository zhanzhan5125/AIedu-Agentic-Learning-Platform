<template>
  <el-aside class="app-aside" width="250px">
    <!-- 用户信息 -->
    <div class="user-info">
      <div class="user-avatar">
        <!-- 用户头像放在这里，可以使用 img 标签或其他组件 -->
        <img src="../views/img/封面.jpg" alt="User Avatar">
      </div>
      <div class="user-details">
        <div class="user-name-title">
          <div class="user-name">{{this.course.title || this.course.tittle}}</div>
        </div>
      </div>
    </div>
    <div style="display: flex;justify-content: center">
      <img src="../views/img/img2.png" height="1" width="200"/>
    </div>
    <div class="content-container">

      <!-- 目录列表 -->
      <el-menu
          :default-active="$route.path" router
          background-color="white"
          text-color="black"
          active-text-color="#2196f3"
          class="el-menu-demo"
          mode="vertical"
          :ellipsis="true"
      >
        <el-menu-item index="/student_course" class="el-menu-item">
          <el-icon name="notebook-2"></el-icon>
          作业
        </el-menu-item>
        <el-menu-item index="/ai_chat" class="el-menu-item">
          <el-icon name="question"></el-icon>
          问答杏台
        </el-menu-item>
        <el-menu-item index="/student_learning">
          <el-icon name="data-analysis"></el-icon>
          我的学情
        </el-menu-item>
        <el-menu-item index="/student_course_map">
          <el-icon name="connection"></el-icon>
          课程路线
        </el-menu-item>
        <el-menu-item index="/student_messages">
          <el-icon name="message"></el-icon>
          <MessageUnreadBadge :offering-id="course.offeringId || course.id || course.courseCode" />
        </el-menu-item>
        <el-menu-item index="/student_resources">
          <el-icon name="reading" ></el-icon>
          资料
        </el-menu-item>
      </el-menu>
    </div>
  </el-aside>
</template>

<script>
import MessageUnreadBadge from '@/components/MessageUnreadBadge.vue'
export default {
  components: { MessageUnreadBadge },
  created() {
    this.course = this.$store.getters.getCourse
    this.user = this.$store.getters.getUser
  },
  data() {
    return {
      user:null,
      course:null,
      selectedDirectory: 'course'
    };
  },
  methods: {

    handleMenuSelect(index) {
      this.selectedDirectory = index;
    },
  },
};
</script>

<style scoped>
/* 根据 Element UI 的样式修改 */
.app-aside {
  margin: 0 auto; /* 居中 */
  align-items: center;
  box-shadow: 5px 0 10px rgba(0, 0, 0, 0.1); /* 添加阴影效果，可以根据需要调整阴影颜色和大小 */
}
.user-info {
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  padding: 20px;
}
.router {
  text-decoration: none;
  color: inherit;
  cursor: pointer;
}
.user-avatar {
  width: 200px;
  height: 100px;
  overflow: hidden;
}
.user-avatar img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.user-details {
  display: flex;
  flex-direction: column;
  justify-content: center;
}
.user-name {
  margin-top: 10px;
  font-weight: bold;
  font-size: 20px;
}
.user-title {
  font-size: 14px;
  color: #888;
}

.el-menu-item {
  font-size: 17px;
  text-align: left;
}

.el-menu-item span {
  display: inline-block;
  vertical-align: middle;
}
.content-container {
  margin-top: 30px;
}
.calendar-container {
  margin-top: auto;
}

/* 月历组件样式 */
/deep/ .el-calendar {
  font-size: 12px;
  width: 300px;
}
/deep/ .el-calendar .next {
  border: none;
}
/deep/ .el-calendar td {
  border: none;
}
/deep/ .el-calendar .el-calendar-day {
  height: 30px !important;
  text-align: center;
  border: none;
}
/deep/ .el-calendar .el-calendar__header {
  justify-content: space-between;
}
/deep/ .el-calendar .is-selected {
  background-color: #1d8dd8;
  color: #fff;
}
</style>
