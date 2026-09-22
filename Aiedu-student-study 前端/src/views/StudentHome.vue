<template>
  <div class="layout-container">

    <!-- Sidebar 和主内容部分 -->
    <div class="main-container">
        <!-- 这里放置你的主要内容 -->
        <main>
          <div class="course-list">
            <div class="search-create">
              <div class="left-text">我上的课</div>
              <el-input
                  placeholder="搜索课程..."
                  v-model="courseSearch"
                  clearable
                  class="search-input"
              >
                <el-button slot="append" icon="el-icon-search" @click="load"></el-button>
              </el-input>
<!--              <el-button type="primary" icon="el-icon-plus" @click="createCourse" class="create-course-btn">添加课程</el-button>-->
            </div>
            <div style="margin-bottom: 20px">
              <el-divider></el-divider>
            </div>
            <div class="course-cards">
              <div v-for="course in courses" :key="course.offeringId || course.courseCode" class="course-card">
                <el-button  @click="gotoCourse(course)"
                            class="course-card-button">
                  <div class="course-content">
                <img src="../views/img/封面.jpg" alt="Course Image" class="course-cover">
                <div class="course-details">
                  <div class="course-title">{{ course.title }}</div>
                  <div class="course-info">
                    <div>课程编号：{{ course.cno }}</div>
                    <div>教师：{{ course.teacher }}</div>
                    <div>教学班：{{ course.sectionCode || '01' }}</div>
                    <div>学年：{{ course.year }}-{{ course.year +1 }}({{course.term}})</div>
                  </div>
                </div></div>
                </el-button>
              </div>
            </div>
          </div>
        </main>
    </div>
  </div>
</template>

<script>
import apiV1 from '@/utils/apiV1'

export default {
  data() {
    return {
      courseSearch:null,
      courses: [],
      image:'https://placekitten.com/883/355',
    };
  },
  created() {
    this.load()
  },
  methods:{
    gotoCourse(course){
      const courseTemp = {
        tittle: course.title,
        cno: course.cno,
        courseNumber: course.cno,
        sectionCode: course.sectionCode,
        sectionName: course.sectionName,
        year: course.year,
        term: course.term,
        teacher: course.teacher,
        offeringId: course.id || course.offeringId || course.courseCode,
        // 旧页面仍以 courseCode 传递开课 ID，迁移完成前保留兼容字段。
        courseCode: course.id || course.offeringId || course.courseCode
      }
      this.$store.dispatch('setCourse',courseTemp)
      const params = {tittle:course.title};
      this.$router.push({
        name:'学生课程',
        params:params })
    },
    async load(){
      try {
        const res = await apiV1.get('/student/courses')
        const keyword = (this.courseSearch || '').trim().toLowerCase()
        const records = (res.data && res.data.records) || []
        this.courses = records
          .filter(course => !keyword || course.title.toLowerCase().includes(keyword) ||
            course.number.toLowerCase().includes(keyword))
          .map(course => ({
            ...course,
            cno: course.number,
            sectionCode: course.section_code,
            sectionName: course.section_name,
            offeringId: course.id
          }))
      } catch (error) {
        this.courses = []
        this.$message.error(error.response?.data?.msg || '课程列表加载失败，请稍后重试')
      }
    },
  }
};
</script>

<style>
.layout-container {
  display: flex;
  flex-direction: column;
  height: 100vh; /* 设置高度为视口的100%，使布局占满整个屏幕 */
}

.main-container {
  display: flex;
  flex: 1; /* 主内容区域占据剩余的空间 */
}
/* 样式 ... */
.home {
  display: flex;
}

main {
  flex: 1;
  padding: 20px;
}

.course-list {
  max-width: 1200px;
  margin: 0 auto;
}

.search-create {
  display: flex;
  align-items: center;
  margin-bottom: 20px;
}
.course-details {
  display: flex;
  flex-direction: column;
  flex: 1;
  padding-left: 20px;
}
.course-content{
  display: flex;
  align-items: stretch;
  width: 100%;
  text-align: left;
}
.course-cover {
  width: 145px;
  min-height: 125px;
  align-self: stretch;
  object-fit: cover;
  border-radius: 6px;
  flex-shrink: 0;
}
.create-course-btn {
  background-color: #0177fb;
  color: #fff;
  padding: 10px;
  border: none;
  cursor: pointer;
  margin-left: 20px;
  float: right;
}
.course-card-button{
  border: 1px solid #ddd;
  border-radius: 8px;
  overflow: hidden;
  width: 100%; /* 使 el-button 充满父容器 */
  height: auto; /* 设置卡片高度 */
  box-sizing: border-box;
  display: flex;
  flex-direction: row;
  padding:10px;
}
.course-cards {
  display: flex;
  flex-wrap: wrap;
  gap: 20px; /* 设置间距 */
}

.course-card {
  flex: 0 0 calc(33.33333% - 20px); /* 一行三个，留出间距 */
  height: auto;
}


.course-title {
  font-size: 18px;
  font-weight: bold;
  margin-bottom: 10px;
  margin-top: 5px;
}

.course-info {
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  font-size: 14px;
  color: #888;
  gap: 6px;
}
.left-text {
  font-size: 20px;
  font-weight: bold;
  margin-right: 20px; /* 可根据需要调整右边距 */
}

.search-input{
  width: 200px; /* 设置输入框宽度 */
}
</style>
