<template>
        <main>
          <div class="course-list">
            <div class="search-create">
              <div class="left-text">{{ course.title || course.tittle }} &nbsp;课程作业</div>
            </div>
            <div style="margin-bottom: 5px">
              <el-divider></el-divider></div>
            <div class="assignment-home">
              <div class="assignment-select">
                筛选
                <el-radio-group v-model="radio" size="small" @change="handleRadioChange">
                  <el-radio :label="1" style="margin-left:15px;">全部</el-radio>
                  <el-radio :label="2">已完成</el-radio>
                  <el-radio :label="3">未完成</el-radio>
                </el-radio-group>
              </div>
              <div class="assignment-list">
                <div v-for="assignment in currentAssignments" :key="assignment.id" class="assignment-card">
                  <el-button @click="gotoAssignment(assignment)"
                             class="assignment-card-button">
                    <div class="assignment-content">
                      <div class="img">

                        <img v-if="'0'===assignment.remainTime" :src="require('../views/img/作业.png')" alt="Assignment Image"
                             style="width: 50px;height: 50px;display:flex;flex-direction:row; filter: grayscale(100%);">
                        <img v-else :src="require('../views/img/作业.png')" alt="Assignment Image"
                          style="width: 50px;height: 50px;display:flex;flex-direction:row;">
                      </div>
                      <div class="info">
                        <div class="left-info">
                          <p style="font-size:20px">{{ assignment.title }}</p>
                          <p style="font-size:13px;margin-top:15px;">{{ assignment.status }}</p>
                        </div>

                        <div class="right-info">
                          <p v-if="'0'!==assignment.remainTime" style="text-align:right;color:orange"> 剩余{{ assignment.remainTime }}
                          </p>
                        </div>

                      </div>
                    </div>

                  </el-button>
                </div>
              </div>
            </div>
          </div>
        </main>
</template>

<script>
import apiV1 from '@/utils/apiV1'

export default {
  data() {
    return {
      user:null,
      course:null,
      radio: 1,
      assignments: [],
      currentAssignments:null
    };
  },
  created() {
    this.user = this.$store.getters.getUser
    this.course = this.$store.getters.getCourse
    this.load()
  },
  methods:{
    async load(){
      const offeringId = this.course.id || this.course.offeringId || this.course.courseCode
      if (!offeringId) {
        this.$message.warning('未选择课程，请返回课程列表后重试')
        this.$router.push({ name: '学生主页' })
        return
      }
      try {
        const res = await apiV1.get('/student/assignments', { params: { offering_id: offeringId } })
        const records = (res.data && res.data.records) || []
        this.assignments = records.map(item => ({
          ...item,
          status: this.statusLabel(item.status),
          backendStatus: item.status,
          remainTime: this.remainingTime(item.end_at),
          startTime: item.start_at,
          endTime: item.end_at,
          isChecked: ['graded', 'returned'].includes(item.status) ? '已批阅' : ''
        }))
        this.handleRadioChange()
      } catch (error) {
        this.assignments = []
        this.currentAssignments = []
        this.$message.error(error.response?.data?.msg || '作业列表加载失败，请稍后重试')
      }
    },
    statusLabel(status) {
      return ({
        not_started: '未完成',
        draft: '作答中',
        submitted: '待批阅',
        ai_grading: '智能批阅中',
        needs_review: '待教师确认',
        graded: '已完成',
        returned: '已完成'
      })[status] || '未完成'
    },
    remainingTime(endAt) {
      if (!endAt) return ''
      const milliseconds = new Date(endAt).getTime() - Date.now()
      if (milliseconds <= 0) return '0'
      const hours = Math.floor(milliseconds / 3600000)
      const days = Math.floor(hours / 24)
      if (days > 0) return `${days}天${hours % 24}小时`
      const minutes = Math.max(1, Math.floor(milliseconds / 60000))
      return hours > 0 ? `${hours}小时` : `${minutes}分钟`
    },
    handleRadioChange() {
      this.currentAssignments = this.assignments.filter(assignment => {
        if (this.radio === 1) {
          return true; // 全部
        } else if (this.radio === 2) {
          return assignment.status === '已完成'; // 已完成
        } else if (this.radio === 3) {
          return assignment.status === '未完成'; // 未完成
        }
        return true; // 默认全部
      });
    },
    isBeforeDeadline(deadline) {
      const currentTimestamp = new Date().getTime();
      const deadlineTimestamp = new Date(deadline).getTime();
      return currentTimestamp < deadlineTimestamp;
    },
    gotoAssignment(assignment){
      console.log(assignment)
      const currentAssignment={
        a_id:assignment.id,
        a_name:assignment.title,
        a_status:assignment.status,
        a_checked:assignment.isChecked,
        a_start_time:assignment.startTime,
        a_end_time:assignment.endTime
      }
      console.log(currentAssignment)
      this.$store.dispatch("setCurrentAssignment",currentAssignment)
      // // 获取当前时间
      // const currentDate = new Date();
      // // 格式化成 "YYYY-MM-DD HH:mm:ss"
      // const formattedDate =
      //     `${currentDate.getFullYear()}-${(currentDate.getMonth() + 1).toString().padStart(2, '0')}` +
      //     `-${currentDate.getDate().toString().padStart(2, '0')} ` +
      //     `${currentDate.getHours().toString().padStart(2, '0')}:${currentDate.getMinutes().toString().padStart(2, '0')}:${currentDate.getSeconds().toString().padStart(2, '0')}`;
      // // 在控制台输出格式化后的时间字符串
      // console.log(formattedDate);
      // 截止前始终允许重新进入作答；“已提交”只代表已有一个提交版本，不代表锁定。
      if (['graded', 'returned'].includes(assignment.backendStatus)) {
        this.$router.push({name:'学生成绩'})
      } else if (this.isBeforeDeadline(assignment.endTime)) {
        this.$router.push({name:'学生作答'})
      } else {
        this.$message.info('作业已截止，成绩经教师确认后可查看')
      }
    },
  }
};
</script>

<style>

.assignment-home {
  display: flex;
  flex-direction: column;
  flex: 1;
  margin-top: 2px;
  height: 100%;
}

.assignment-select {
  padding: 10px 10px;
}
main {
  flex: 1;
}

.assignment-list {
  width: 100%;
  margin: 0 auto;
}

.search-create {
  display: flex;
  align-items: center;
  margin-bottom: 20px;
}


.assignment-content {
  display: flex;
  width: 100%;
  height: 100%; /* 保持包装容器高度和 el-button 一致 */
  flex-direction: row;
}
.img {
  width:52px;
  height:52px;
  display: flex;
  flex-direction: row;
  flex-basis:60px;
}
.info {
  display: flex;
  flex-direction:row;
  flex:auto;
}

.assignment-card-button {
  border: 1px solid #ddd;
  border-radius: 8px;
  overflow: hidden;
  width: 100%; /* 使 el-button 充满父容器 */
  height: auto; /* 设置卡片高度 */
  box-sizing: border-box;
  padding: 10px;
  margin-bottom: 10px;
}
.left-info{
  height:auto; 
  text-align: left;
  flex:1;
}
.right-info{
  margin-top:20px;
  flex:1;
}
.assignment-card {
  width: 100%;
  height: auto;
}

.assignment-card img {
  width: 100%;
  height: auto;
}


.left-text {
  font-size: 20px;
  font-weight: bold;
  margin-right: 20px; /* 可根据需要调整右边距 */
}




</style>
