<template>
  <div>
    <div class="wrapper" style="width: 100%;display: flex;padding-top:0;border-bottom: 1px solid #ccc;">
      <p style="font-size: larger; color: #2196f3;  padding-bottom: 17px;padding-top:17px;padding-left:70px">
        {{ course.title || course.tittle }}</p>
      <el-menu
          :default-active="'/assignment'" router
          background-color="white"
          text-color="black"
          active-text-color="#2196f3"
          class="el-menu-demo"
          mode="horizontal"
          :ellipsis="true"
          style="flex-grow: 1; display: flex; justify-content: flex-end;border-bottom: none;padding-right:50px"
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
    <el-main style="height:85vh;overflow-y: auto">
      <div class="title-container">
        <span class="title">{{this.currentAssignment.a_name}}&nbsp;详情统计</span>
        <router-link type="primary"  class="router" to="/checkassignment">返回</router-link>
      </div>
    <div style="display: flex;flex-direction: column">
      <div  class="title"  style="margin-left: 10%;margin-right:10%;display: flex;flex-direction: column">
        <div style="display: flex;flex-direction: row;align-items: center;justify-content: center">
          <div style="display: flex;flex-direction: column">
            <p style="color: #409dfd;">智能点评</p>
            <p  style="font-size: 16px;
             font-weight:normal;color: #888888">输入提示词</p>
          </div>
          <textarea disabled ref="textarea" class="chat-input" v-model="promptCheck" @input="adjustTextareaHeight" ></textarea>
          <el-tooltip content="完成 FastAPI AI 总结接口和模型配置后开放" placement="top">
            <span><el-button disabled type="primary" size="medium" style="margin-top: 10px">AI 总结（待配置）</el-button></span>
          </el-tooltip>
        </div>
        <div v-loading="this.loading"
             v-show="this.visible"
             style="min-height: 100px;font-size: 16px;
             font-weight:normal;color: #000000;border:2px solid rgba(132, 191, 255, 0.5);
             padding:20px;word-break: break-all; white-space: pre-wrap;margin-top: 20px">
          {{this.llmSummary}}</div>
      </div>
      <div class="title" style="color: #409dfd;margin-left: 10%;margin-top: 20px">
        智能统计
      </div>
      <div style="display: flex;flex-direction: row;margin-top: 20px;align-items: center;justify-content: center">
        <div style="display: flex;flex-direction: column;margin-right: 50px">
          <div style="display: flex;flex-direction: row">
            <p style="font-size: 18px; color: #888888;margin-top: 10px">平均分:</p>
            <p style="font-size: 29px; color: #2196f3">{{this.ave_score}}</p>
            <p style="font-size: 18px; color: #888888;margin-top: 10px">分</p>
          </div>
          <div style="display: flex;flex-direction: row;margin-top: 30px">
            <p style="font-size: 18px; color: #888888;margin-top: 10px">最高分:</p>
            <p style="font-size: 29px; color: #6be6c1">{{ this.max_score }}</p>
            <p style="font-size: 18px; color: #888888;margin-top: 10px">分</p>
          </div>
          <div style="display: flex;flex-direction: row;margin-top: 30px">
            <p style="font-size: 18px; color: #888888;margin-top: 10px">最低分:</p>
            <p style="font-size: 29px; color: #626c91">{{ this.min_score }}</p>
            <p style="font-size: 18px; color: #888888;margin-top: 10px">分</p>
          </div>
        </div>
        <!-- DOM -->
        <div id="demo" style="width: 50%"></div>
        <!-- END -->
      </div>
    </div>
    </el-main>
  </div>
</template>


<script>

// 引入echarts
import * as ets from 'echarts'

// 引入主题配置文件
import theme from '../utils/student-study.json'
import apiV1 from '@/utils/apiV1'

export default {
  data() {
    return {
      course:null,
      user:null,
      currentAssignment:'',
      data:null,
      ave_score:null,
      max_score:null,
      min_score:null,
      llmSummary:null,
      summaryNum:null,
      promptCheck:'我将给你若干条作业题目的批阅信息。请你总结该题目的总体作答情况。',
      loading:false,
      visible:false
    };
  },
  created() {
    this.user = this.$store.getters.getUser;
    this.course = this.$store.getters.getCourse;
    this.currentAssignment = this.$store.getters.getCurrentAssignment;
    this.summaryNum = this.$store.getters.getSummary;
    // this.$store.dispatch('setSummary',this.currentAssignment.submit_num-this.currentAssignment.left_num)
  },
  async mounted() {
      try {
        const [insightRes,submissionRes]=await Promise.all([
          apiV1.get(`/teacher/assignments/${this.currentAssignment.a_id}/insights`),
          apiV1.get(`/teacher/assignments/${this.currentAssignment.a_id}/submissions`)
        ])
        const insight=insightRes.data
        this.data=[{value:insight.submitted_count,name:'已提交'},{value:Math.max(insight.assigned_count-insight.submitted_count,0),name:'未提交'}]
        const scores=submissionRes.data.records.filter(item=>['graded','returned'].includes(item.status)).map(item=>item.total_score)
        this.min_score=scores.length?Math.min(...scores):0
        this.max_score=scores.length?Math.max(...scores):0
        this.ave_score=insight.average_score
        // 注册主题(参数1: 使用时的别名 参数2: 主题配置文件)
        ets.registerTheme('theme', theme)
        // 初始化图表
        var myChart = ets.init(document.getElementById('demo'), theme)
        myChart.setOption({

          series: [
            {
              type: 'pie',
              radius: '80%',
              center: ['30%', '50%'],
              data:this.data,
              lineStyle: {
                width: 1
              },
              label: {
                color:'#ffffff',
                textStyle: {  // 添加textStyle属性来设置字体大小
                  fontSize: 16  // 设置字体大小
                },
                show: true,  // 是否显示标签
                position: 'inside',  // 标签位置，可选值为 'inside', 'outside', 'center'
                formatter: '{d}%',  // 标签内容格式器，{a}:系列名，{b}:数据名，{c}:数据值，{d}:百分比
              }
            }
          ],
          legend: {
            orient: 'vertical',
            right: '10%',
            top: 'center',
            itemGap: 30,
            itemWidth: 20,
            itemHeight: 20,
            textStyle: {  // 添加textStyle属性来设置字体大小
              fontSize: 16  // 设置字体大小
            },
            formatter: function (name) {
              // 获取当前图例项的值
              var value = myChart.getOption().series[0].data.find(item => item.name === name).value;
              return name + ': ' + value + '人';
            },
            data: this.data.map(item => item.name)
          }
        })
      } catch (error) { this.$message.error(error.response?.data?.msg||'作业统计加载失败') }
  },
  methods:{
    adjustTextareaHeight() {
      const textarea = this.$refs.textarea; // 使用 $refs 获取 textarea 元素
      textarea.style.height = "auto"; // 重置高度，以便重新计算
      textarea.style.height = `${Math.min(textarea.scrollHeight, 200)}px`; // 设置高度，并限制最大高度为200px
    },
    async goToSummary() {
      this.visible = true
      this.loading = true
        try {
          const created=await apiV1.post('/ai/summary-jobs',{resource_id:this.currentAssignment.a_id,idempotency_key:`summary-${this.currentAssignment.a_id}-${Date.now()}`,prompt:this.promptCheck})
          for(let attempt=0;attempt<60;attempt++){
            const job=await apiV1.get(`/jobs/${created.data.job_id}`)
            if(job.data.status==='succeeded'){this.llmSummary=job.data.result?.summary||job.data.result?.content||JSON.stringify(job.data.result);break}
            if(job.data.status==='failed')throw new Error(job.data.error||'总结失败')
            await new Promise(resolve=>setTimeout(resolve,1000))
          }
        } catch (error) {
          console.error('大模型总结失败...', error)
        }
      this.loading = false
    },
    load(){}
  }
}
</script>

<style>
#demo{
  height: 300px;
  width: 800px;
}
.title {
  display: block;
  font-size: 20px;
  color: black;
  font-weight: bold;
  margin-left: 70px;
}

.title-container {
  border-bottom: 1px solid #ccc;
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
  padding: 5px 20px 10px;
}.router{
   text-decoration: none; /* 去掉下划线 */
   color: #0177FBFF; /* 保持默认文字颜色 */
   cursor: pointer; /* 添加手型光标 */
   font-size: 13px;
  margin-right: 80px;
 }
 .chat-input:focus{
   border-color: #409dfd;
   outline: none;
 }
.chat-input {
  font-size: large;
  flex-grow: 1;
  border: 2px solid rgba(132, 191, 255, 0.5);
  padding: 5px;
  min-height: 20px; /* 设置最小高度，以确保始终有一定的高度 */
  word-break: break-all;
  white-space: pre-wrap;
  overflow-wrap: break-word;
  display: flex; /* 使用 flex 布局 */
  align-items: center; /* 上下居中 */
  border-radius: 5px;
  box-sizing: border-box;
  transition: border-color 0.3s;
  margin-right: 20px;
  resize: none; /* 防止用户手动调整 textarea 的大小 */
  overflow-y: auto; /* 在内容溢出时显示滚动条 */
  margin-top: 10px;
  margin-left: 20px;
}

</style>
