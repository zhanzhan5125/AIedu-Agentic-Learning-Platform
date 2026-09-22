<template>
  <div class="total-container">

    <!--导航栏-->
    <div class="header-container"
         style="width: 100%; height: auto; display: flex;padding-top:0;border-bottom: 1px solid #ccc;">
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

    <el-main style="height:75vh;padding-bottom: 0;">

      <!--页面标题栏-->
      <div class="title-container">
        <span class="title">{{ this.currentAssignment.a_name }}&nbsp;智能批阅</span>
        <router-link type="primary" class="router" to="/checkassignment">返回</router-link>
      </div>

      <!--提示词撰写模块-->
      <div class="prompt-container">

        <div class="prompt-box">
          <div class="prompt-left">
            <p style="line-height: 40px;font-weight: bold;margin-left: 20px;margin-top: 10px">批阅模式</p>
            <div v-for="(prompt,index) in promptList" :key="index">
              <div class="prompt-grid" :class="{ 'activeGrid': activeGrid === index }">
                <div class="prompt-grid-content clickable" style="display:flex;" @click="selectPrompt(index)">
                  <div class="prompt-grid-left" style="width: 80%;text-align: center">
                    <p style="line-height: 40px">{{ prompt.name }}</p>
                  </div>
                  <div class="prompt-grid-middle"
                       style="width:20%;display: flex; justify-content: center;align-items: center">
                    <i class="el-icon-check" v-if="prompt.ptStatus ===1"></i>
                  </div>
                  <!--                  <div class="prompt-grid-right"-->
                  <!--                       style="width:30%;display: flex; justify-content: center;align-items: center">-->
                  <!--                    <el-dropdown trigger="click">-->
                  <!--                      <el-button type="primary" icon="el-icon-more" style="height:30px"></el-button>-->
                  <!--                      <el-dropdown-menu slot="dropdown">-->
                  <!--                        <el-dropdown-item>-->
                  <!--                          <el-button style="border:none" @click="changePrompt()">设为启用</el-button>-->
                  <!--                        </el-dropdown-item>-->
                  <!--                      </el-dropdown-menu>-->
                  <!--                    </el-dropdown>-->
                  <!--                  </div>-->
                </div>
              </div>
            </div>
            <p style="line-height: 40px;font-weight: bold;margin-left: 20px;margin-top: 10px">批阅模型</p>
            <div class="prompt-grid">
              <div class="prompt-grid-content clickable" style="display:flex;">
                <div class="prompt-grid-left" style="width: 100%;text-align: center">
                  <select v-model="llm" style="border: none; font-size: larger;line-height: 40px; font-weight: bold; color: rgb(1,21,33); width: 100%; height: 45px; text-align: center;">
                    <option v-for="option in options" :key="option.value" :value="option.value">
                      {{ option.label }}
                    </option>
                  </select>





                </div>
              </div>
            </div>
            <div class="prompt-grid" style="margin-top: 100px;background-color: #e4effc;">
              <div class="prompt-grid-content clickable" style="display:flex;" @click="llmCheck()">
                <div class="prompt-grid-left" style="width: 100%;text-align: center">
                  <p style="line-height: 40px;font-weight: bold;color: rgb(1,21,33)">一键智能批阅</p>
                </div>
              </div>
            </div>
            <!--            <div class="mode-selector" style="width:100%;height:40px;justify-content: center;align-items: center;display: flex;padding-top:10px">-->
            <!--              <el-switch-->
            <!--                  style="zoom: 1.1"-->
            <!--                  v-model="preview"-->
            <!--                  active-text="预览模式"-->
            <!--                  inactive-text="编辑模式"-->
            <!--                  @change="changeStyle()">-->
            <!--                >-->
            <!--              </el-switch>-->
            <!--            </div>-->

            <!--            <div class="prompt-grid">-->
            <!--              <div class="prompt-grid-content clickable" style="display:flex;" @click="addPrompt()">-->
            <!--                <div class="prompt-grid-left" style="width: 100%;text-align: center">-->
            <!--                  <p style="line-height: 40px;font-weight: bold">新建提示词</p>-->
            <!--                </div>-->
            <!--              </div>-->
            <!--            </div>-->
          </div>

          <div class="prompt-middle">
            <div v-for="(item,index) in promptList[activeGrid].prompt" :key="index">
              <div class="text-grid">
                <div class="text-upper"
                     :style="{ height: '30px', backgroundColor: index > 0 ? '#EAF4FD' : 'rgb(64,158,255)' }">
                  <p style="line-height: 30px;margin-left: 10px">
                    {{ index > 0 ? '问答' + (index) : '角色设定' }}
                  </p>
                </div>
                <div class="text-bottom" v-show="!preview">
                  <el-input
                      type="textarea"
                      :autosize="{ minRows: 2}"
                      placeholder="请输入内容"
                      v-model="item.value"
                      style="border: none; box-shadow: none; font-size: 15px; overflow-y: hidden;">
                  </el-input>
                </div>
                <div class="preview" v-show="preview"
                     style="font-size: 15px; overflow-y: hidden;min-height:58px;width:100%;font-family:华文宋体;">
                  <span v-html="item.value" style="line-height:25px"></span>
                </div>
              </div>
            </div>

            <div class="middle-button" v-show="!preview" style="height:35px;width:90%;margin: 10px auto 10px;">
              <el-button type="primary" plain icon="el-icon-plus" style="height:35px" @click="addRound()">增加对话
              </el-button>

              <el-popconfirm
                  confirm-button-text='确定'
                  cancel-button-text='我再想想'
                  icon="el-icon-info"
                  icon-color="red"
                  title="你确定删除吗？"
                  @confirm="subRound()"
                  class="ml-5"
              >
                <el-button slot="reference" type="danger" plain icon="el-icon-delete" style="height:35px" @click="">
                  删除对话
                </el-button>
              </el-popconfirm>
              <el-button type="success" plain icon="el-icon-check" style="height:35px;margin-left: 5px"
                         @click="savePrompt()">保存更改
              </el-button>
            </div>
          </div>

          <div class="prompt-right">
            <div class="right-upper"
                 style="height:40px;margin: 0 10px 5px 10px;background-color:#C8C8C9;text-align: center;font-size:16px;border-radius: 4px ">
              <span style="line-height: 40px">可用模块</span>
            </div>
            <div class="right-bottom">
              <div v-for="(key,index) in keyList" :key="index">
                <el-tooltip class="item" effect="light" :content="key.info" placement="left">
                  <div class="key-grid">
                    <div class="key-content" style="width: 100%;text-align: center;background-color: #EAF4FD">
                      <p style="line-height: 30px">{{ key.name }}</p>
                    </div>
                  </div>
                </el-tooltip>
              </div>
            </div>
          </div>
        </div>
      </div>

    </el-main>
    <div class="log-container">
      <div class="log-box">
        <div class="log-upper" style="width: 100%;height: 50px;border-bottom: solid 1px rgb(200,200,201);display: flex">
          <div class="log-title" style="width:14%;text-align: center">
            <span style="line-height: 50px;font-size:20px;font-weight: bold">批阅进度</span>
          </div>
          <div v-if="loading" style="margin-right: 15px;margin-top: 13px">
            <i class="el-icon-loading" style="color: #409dfd"></i> <i style="color: #409dfd">正在批阅中</i>
          </div>
          <div class="custom-loading" v-if="loading" style="margin-top: 15px;width: 1000px">
            <el-progress :percentage="progressPercent" :stroke-width="10" show-text></el-progress>
          </div>
        </div>
        <!--        <div class="log-bottom">-->
        <!--          <div v-for="(item,index) in logList" :key="index">-->
        <!--            <div class="log-grid" style="margin:20px auto;width: 95%;box-shadow: 0 2px 4px rgba(0, 0, 0, .12), 0 0 6px rgba(0, 0, 0, .04)">-->
        <!--              <div style="=height:30px;width:100%;display: flex">-->
        <!--                <span style="line-height: 30px;margin-left: 20px">学生学号：{{item.name}}</span>-->
        <!--                <span style="line-height: 30px;margin-left: 20px">得分：{{item.score}}</span>-->
        <!--              </div>-->
        <!--              <div style="margin-left: 20px">-->
        <!--                <span style="line-height: 30px;">评价：{{item.content}}</span>-->
        <!--              </div>-->
        <!--            </div>-->
        <!--          </div>-->

        <!--        </div>-->
      </div>
    </div>
  </div>
</template>

<script>
import apiV1 from '@/utils/apiV1'
export default {
  data() {
    return {
      options:[
        {
          value:'Qwen-max',
          label:'Qwen-max'
        }, {
          value:'Qwen-plus',
          label:'Qwen-plus'
        }
      ],
      llm:'Qwen-max',
      preview: true,
      course: null,
      round: 0,
      activeName: 'second',
      currentAssignment: '',
      promptList: [],
      loading:false,
      stuList:[],
      logList:[
        {
          name:"333100202",
          score:"9",
          content:"哈哈哈哈哈哈哈"
        },

      ],
      progressPercent: 0,
      keyList: [
        {
          name: "题目内容",
          info: "作业的一道题目的题干"
        }, {
          name: "正确答案",
          info: "作业的一道题目的正确解答"
        }, {
          name: "学生答案",
          info: "学生作答某道题目的内容"
        }, {
          name: "题目分值",
          info: "作业的一道题目的满分"
        }, {
          name: "期望分值",
          info: "题目的满分 * 0.7,仅供作返回示例"
        }
      ],
      activeGrid: 0,
    };
  },

  created() {
    this.user = this.$store.getters.getUser
    this.course = this.$store.getters.getCourse;
    this.stuList = this.$store.getters.getStuList;
    this.currentAssignment = this.$store.getters.getCurrentAssignment;
    this.load();
  },

  methods: {
    load(){
      this.promptList=[]
      apiV1.get('/prompts').then(res => {
        function parseStringToDictList(prompt) {
          let dictList = []
          let array = prompt.split(/\$/);
          for (let i = 0; i < array.length; i++) {
            dictList.push({"value": array[i]})
          }
          return dictList;
        }

        let promptList = res.data
        for (let i = 0; i < promptList.length; i++) {
          let dictionary = {
            name: promptList[i].name,
            purpose: promptList[i].purpose,
            ptId: promptList[i].id,
            prompt: parseStringToDictList(promptList[i].content||''),
            ptStatus: promptList[i].active
          }
          this.promptList.push(dictionary)
          console.log("promptList", this.promptList)
        }
        this.changeStyle()
        this.selectPrompt(0)
      })
    },
    handleClick(tab, event) {
      console.log(tab, event);
    },
    addRound() {
      this.promptList[this.activeGrid].prompt.push({
        value: ""
      })
      this.changeKeyList()
    },
    subRound() {
      this.promptList[this.activeGrid].prompt.pop()
      this.changeKeyList()
    },
    selectPrompt(index) {
      this.activeGrid = index;
      this.changeKeyList()
      console.log(prompt.name)
    },
    changeKeyList() {
      for (let i = 0; i < this.round; i++) {
        this.keyList.pop()
      }
      this.round = this.promptList[this.activeGrid].prompt.length - 2
      for (let i = 0; i < this.round; i++) {
        this.keyList.push({
          "name": "问答" + (i + 1) + "评语",
          "info": "问答" + (i + 1) + "返回的评语"
        })
      }
    },
    llmCheck() {
      this.loading = true;
      const pendingReviewStudents = this.stuList.filter(student => student.isChecked === '待批阅');
      const totalStudents = pendingReviewStudents.length;
      let completedStudents = 0;
      const updateProgress = () => {
        this.progressPercent = Math.round((completedStudents / totalStudents) * 100);
      };

      const processNextStudent = (index) => {
        if (index < totalStudents) {
          const student = pendingReviewStudents[index];
          apiV1.post('/ai/grading-jobs', {resource_id:student.submissionId,idempotency_key:`grading-${student.submissionId}-${Date.now()}`})
              .then(response => {
                // 处理成功情况
                console.log(response);
              })
              .catch(error => {
                // 处理失败情况
                console.error(error);
              })
              .finally(() => {
                // 处理下一个学生
                completedStudents++;
                updateProgress();
                processNextStudent(index + 1);
              });
        } else {
          // 所有学生处理完毕，重新加载数据
          this.loading = false;
          this.load();
        }
      };
      // 开始处理第一个学生
      processNextStudent(0);
    },
    savePrompt() {
      let promptList = this.promptList[this.activeGrid].prompt
      let promptString = ""
      for (let i = 0; i < promptList.length; i++) {
        if (i != 0) promptString += "$"
        promptString += promptList[i]['value']
      }
      const selected=this.promptList[this.activeGrid]
      apiV1.post(`/prompts/${selected.ptId}/versions`, {name:selected.name,purpose:selected.purpose||'grading',content:promptString,activate:selected.ptStatus}).then(response => {
        console.log(response);
        this.$message.success("保存成功")
      })
    },
    changeMode() {
      this.preview = !(this.preview)
      this.changeStyle()
    },
    changeStyle() {
      function replaceHtmlTags(str) {
        // 匹配span标签的开始标签和结束标签
        var regex = /<span\b[^>]*>(.*?)<\/span>/g;
        // 使用replace方法替换匹配的标签
        var replacedStr = str.replace(regex, function (match, p1) {
          // 将span标签的开始标签替换为"{{"，结束标签替换为"}}"
          return "{{" + p1 + "}}";
        });
        return replacedStr;
      }

      if (this.preview) {
        for (let j = 0; j < this.promptList.length; j++) {
          for (let i = 0; i < this.promptList[j]['prompt'].length; i++) {
            let reply = this.promptList[j]['prompt'][i]['value']
            this.promptList[j]['prompt'][i]['value'] = reply.replace(/\{\{(.*?)\}\}/g, '<span style="color: white;background-color:#409EFF;line-height:30px;border-radius: 2px;margin:0 4px">$1</span>').replace(/\n/g, '<br>');
          }
        }
      } else {
        for (let j = 0; j < this.promptList.length; j++) {
          for (let i = 0; i < this.promptList[j]['prompt'].length; i++) {
            let reply = this.promptList[j]['prompt'][i]['value']
            this.promptList[j]['prompt'][i]['value'] = replaceHtmlTags(reply).replace(/<br>/g, '\n')
          }
        }
      }
    }
  }
}
</script>

<style scoped>

.title {
  display: block;
  font-size: 20px;
  color: black;
  font-weight: bold;
  margin-left: 70px;
}
.el-main{
  padding: 20px 10px 0 20px !important;
}
.title-container {
  border-bottom: 1px solid #ccc;
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
  padding: 5px 20px 10px;
}

.router {
  text-decoration: none; /* 去掉下划线 */
  color: #0177FBFF; /* 保持默认文字颜色 */
  cursor: pointer; /* 添加手型光标 */
  font-size: 13px;
  margin-right: 80px;
}

.prompt-container {
  height: 300px;
  width: 100%;
  margin-top: 30px;
}

.prompt-box {
  display: flex;
  height: 440px;
  width: 85%;
  margin: 0 auto;
  box-shadow: 0 2px 12px 0 rgba(0, 0, 0, 0.1);
}

.prompt-left {
  width: 22%;
  height: 100%;
  background-color: #C8C8C9;
}

.prompt-middle {
  width: 60%;
  height: 100%;
  overflow-y: auto;
}

.prompt-right {
  width: 18%;
  height: 420px;
  border-left: solid 1px #C8C8C9;
  margin-top: 10px;
  margin-bottom: 10px;
}

.prompt-grid {
  height: 50px;
  width: 90%;
  margin: 10px auto 10px;
  background-color: white;
  border-radius: 5px;
  padding: 5px;
}

.clickable {
  cursor: pointer; /* 将鼠标样式改为手指 */
}

.clickable:hover {
  background-color: rgb(229, 241, 252); /* 鼠标悬停时的背景色 */
  color: black;
}

.activeGrid {
  background-color: black;
  color: white;
}

.text-grid {
  min-height: 78px;
  width: 90%;
  margin: 10px auto 10px;
  box-shadow: 0 2px 12px 0 rgba(0, 0, 0, 0.1);
  border-radius: 5px;
}

.preview {
  display: block;
  resize: vertical;
  padding: 5px 15px;
  line-height: 1.5;
  box-sizing: border-box;
  width: 100%;
  font-size: inherit;
  color: #606266;
  background-color: #FFF;
  background-image: none;
  border: 1px solid #DCDFE6;
  border-radius: 4px;
  transition: border-color .2s cubic-bezier(.645, .045, .355, 1);
}

.key-grid {
  height: 40px;
  width: 90%;
  margin: 10px auto 10px;
  background-color: #EAF4FD;
  border-radius: 5px;
  padding: 5px;
  text-align: center;
}

.log-container {
  height: 70px;
  width: 100%;
  padding: 0 10px 20px 20px;
}

.log-box {
  height: 50px;
  width: 85%;
  margin: 0 auto;
  box-shadow: 0 2px 12px 0 rgba(0, 0, 0, 0.1);
  background-color: #FFFFFF;
}
</style>
