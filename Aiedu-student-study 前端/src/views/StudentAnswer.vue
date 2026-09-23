<template>
  <div id="content" class="content" >
<!--    :style="{ width: windowWidth + 'px', height: windowHeight + 'px' }"-->
  <div class="answer-container" style="display: flex; flex-direction: column">
    <div class="answer-header"
         style="height: 60px; width: 100%; border-bottom: 3px solid #ccc; display: flex; justify-content: space-between;">
      <div class="left-side" style="height: 100%;margin-left:20px">
        <div class="left-upper" style="font-size:18px;margin-top:3px">
          <p>{{this.assignment.a_name}}</p>
        </div>
        <div class="left-bottom" style="color:#BFBFBF;margin-top:3px;font-size:14px;display:flex;">
          <p>题量:&nbsp&nbsp</p>
          <p>{{this.totalItem}}</p>
          <p style="margin-left:20px">满分:&nbsp&nbsp</p>
          <p>{{ this.total_score }}</p>
          <p style="margin-left:20px">作答时间:&nbsp&nbsp</p>
          <p>{{this.assignment.a_start_time}}&nbsp&nbsp</p>
          <p>至&nbsp&nbsp</p>
          <p>{{this.assignment.a_end_time}}</p>
        </div>
      </div>
      <div class="right-side" style="height: 100%; line-height: 57px;margin-right:20px">
        <el-button type="primary" style="width:100px" round @click="submit(0)" :disabled="buttonDis || isDisabled">保存</el-button>
        <el-button type="primary" style="width:100px" round @click="submit(1)" :disabled="buttonDis || isDisabled">提交</el-button>
        <el-button type="info" style="width:100px;margin-right: 50px" round @click="returnTo()">返回</el-button>
      </div>
    </div>

    <div class="answer-bottom" style="height: 100%; width:99%; display: grid; grid-template-columns: 300px 1fr;">
      <div class="answer-aside" style="background-color: #EAF4FD; border-right: 1px solid #ccc;">
        <div class="block" style="width:100%;height:20px;background-color: #EAF4FD"></div>
        <div class="answer-problems"
             style="background-color: white;margin-left: 20px;margin-right:20px;border-radius: 20px;padding:15px">
          <div class="answer-title" style="display:flex;height:30px;width:100%">
            <p style="font-size:18px">题目列表</p>
            <div style="font-size:16px;display: flex;margin-top:2px">
              <p style="margin-left: 6px">(</p>
              <p>{{ total_score }}</p>
              <p>分)</p>
            </div>
          </div>
          <div class="answer-body" style="height:100px;width:100%;margin-top:10px">
            <el-row :gutter="20">
              <el-col :span="6" v-for="item in tableData" :key="item.porder" :offset="0">
                <el-button
                    :class="{ activeButton: item.porder === p_now }"
                    style="height: 40px; width: 40px; margin-bottom: 20px; border: 2px solid #409EFF; border-radius: 6px; display: flex; justify-content: center; align-items: center;"
                    @click="changeProblem(item.porder)"
                >
                  <p :style="{ color: item.porder === p_now ? 'white' : '#409EFF', fontSize: '20px' }">{{ item.porder }}</p>
                </el-button>
              </el-col>
            </el-row>
          </div>
        </div>
      </div>
      <div class="answer-sheet" style="padding: 30px;overflow-x:hidden">
        <div class="sheet-inside" style="border:2px solid #E4EDF8;padding:20px">
          <div class="problem-title" style="word-break: break-all; white-space: pre-wrap;">
            <p>第{{this.p_now}}题({{this.score}}分)</p>
            <p>&nbsp;</p>
            <p style="margin: 0;line-height: 20px;text-align: left;display: inline;color: black;">
                {{this.p_main}}
            </p>
          </div>
          <div style="margin-top:20px;">
<!--            <el-input-->
<!--                type="textarea"-->
<!--                :autosize="{ minRows: 18,maxRows:18}"-->
<!--                placeholder="请输入答案"-->
<!--                v-model="content"-->
<!--                :disabled="this.isDisabled"-->
<!--                style="font-size: 15px"-->
<!--                @keydown.tab.native="tabInput($event)"-->
<!--            >-->
<!--            </el-input>-->
            <quill-editor
                ref="myQuillEditor"
                v-model="content"
                :options="editorOption"
                @blur="onEditorBlur($event)"
                @focus="onEditorFocus($event)"
                @ready="onEditorReady($event)"
                @change="onEditorChange($event)"
                class="ql-container"
            />
<!--             图片上传组件辅助，组件内添加v-show=“false”属性，把该组件隐藏起来。-->
          </div>
        </div>
        <div style="text-align: center">
          <el-button :disabled="isFirstItem" type="primary" round style="width:140px;margin-top:20px;text-align: center" @click="lastItem()">上一题</el-button>
        <el-button :disabled="isLastItem" type="primary" round style="width:140px;margin-top:20px;text-align: center" @click="saveItem()">下一题</el-button>
          </div>
      </div>
    </div>
  </div>
  </div>
</template>


<script>
import 'quill/dist/quill.core.css'
import 'quill/dist/quill.snow.css'
import 'quill/dist/quill.bubble.css'
import {quillEditor} from 'vue-quill-editor'
import apiV1 from '@/utils/apiV1'

const toolbarOption = [
  [{ list: "ordered" }, { list: "bullet" }],
  ['clean']
]
export default {
  components: {
    quillEditor
  },
  name: "Answer",
  data() {
    return {// 保存编辑器的内容
      editorOption: { // 初始化 editorOption 属性
        // 编辑器选项，可以根据需要进行配置
        placeholder: '请输入你的回答..',
        modules: {
          toolbar: {
            container:toolbarOption
          }
        }
      },
      user:null,
      course:null,
      assignment:null,
      isFirstItem:true,
      isLastItem:false,
      totalItem:3,
      p_now:1,
      hs_num: 7,
      total_score:0,
      tableData: [],
      p_main:"",
      content:"",
      isDisabled:false,
      submitTime:0,
      score:0,
      // 缩放比
      screenRatio: Math.round((window.outerWidth / window.innerWidth) * 100),
      windowWidth: window.innerWidth,
      windowHeight: window.innerHeight,
      uploadUrl:'/student/course/assignment/stuAssignment/image',
      headers:{ enctype:'multipart/form-data'},
      newFileName:null,
      imageNum:1,
      fileList:[],
      buttonDis:false
    }
  },
  created() {
    window.onload = window.onresize = function() {
      document.body.style.zoom = 1;
    };
    this.user = this.$store.getters.getUser
    this.course = this.$store.getters.getCourse
    this.assignment = this.$store.getters.getCurrentAssignment
    if(!this.assignment || !this.isBeforeDeadline(this.assignment.a_end_time)){
      this.isDisabled = true

    }
    this.load()
  },
  mounted() {
    //  自定义粘贴图片功能
    // let quill = this.$refs.myQuillEditor.quill
    // this.$forceUpdate()
    // quill.root.addEventListener('paste', evt => {
    //   if (evt.clipboardData && evt.clipboardData.files && evt.clipboardData.files.length) {
    //     evt.preventDefault();
    //     [].forEach.call(evt.clipboardData.files, file => {
    //       if (!file.type.match(/^image\/(gif|jpe?g|a?png|bmp)/i)) {
    //         return
    //       }
    //       const currentDate = new Date();
    //       const timestamp = currentDate.getTime(); // 获取当前时间戳（毫秒）
    //       const formattedDate = currentDate.toISOString().slice(0, 19).replace(/[-:]/g, ''); // 格式化时间为 "YYYYMMDDHHmmss"
    //       this.newFileName = `${this.user.name}_${this.assignment.a_id}_${this.p_now}_${this.imageNum}_${formattedDate}`;
    //       const formData = new FormData();
    //       const newFile = new File([file], this.newFileName, { type: file.type });
    //       formData.append("file", newFile);//后台上传接口的参数名
    //       // formData.append('fileName', this.newFileName);
    //       console.log(formData.get('file'))
    //       let config = {
    //         headers: {
    //           'Content-Type': 'multipart/form-data'
    //         }
    //       };
    //       this.uploadUrl += '?fileName='+this.newFileName
    //       this.axios.post(this.uploadUrl,formData,config).then(
    //           res=>{
    //             // 如果上传成功
    //             if (res.code !== 0) {
    //               // 获取光标所在位置
    //               let length = quill.getSelection().index;
    //               // 插入图片，res为服务器返回的图片链接地址
    //               quill.insertEmbed(length, 'image', res.data)
    //               // 调整光标到最后
    //               quill.setSelection(length + 1)
    //             } else {
    //               // 提示信息，需引入Message
    //               this.$message.error('图片插入失败！')
    //             }
    //           }
    //       )
    //     })
    //   }
    // }, false)
      // 自定义粘贴图片功能
      let quill = this.$refs.myQuillEditor.quill;
      this.$forceUpdate();
      quill.root.addEventListener('paste', evt => {
        if (evt.clipboardData && evt.clipboardData.items) {
          for (let i = 0; i < evt.clipboardData.items.length; i++) {
            if (evt.clipboardData.items[i].type.indexOf('image') !== -1) {
              // 是图片，弹出提示信息
              evt.preventDefault();

              // 弹出提示信息
              this.$message.info('请点击图片按钮上传图片');

              // 清除剪贴板内容
              evt.clipboardData.clearData();
            }
          }
        }

      });
  },
  methods:{
    //失去焦点事件
    onEditorBlur(quill) {
      console.log('editor blur!', quill)
    },
    //获得焦点事件
    onEditorFocus(quill) {
      console.log('editor focus!', quill)
    },
    // 准备富文本编辑器
    onEditorReady(quill) {
      console.log('editor ready!', quill)
      if (this.isDisabled) {
        quill.disable(); // 禁用编辑器
      }
    },
    //内容改变事件
    onEditorChange({ quill, html, text }) {
      console.log('editor change!', quill, html, text)
      this.content = html
    },
      isBeforeDeadline(deadline) {
      const currentTimestamp = new Date().getTime();
      const deadlineTimestamp = new Date(deadline).getTime();
      return currentTimestamp < deadlineTimestamp;
    },
    changeProblem(item){
      this.tableData[this.p_now-1].stuAns = this.formatContent(this.content);
      this.p_now=item;
      this.check();
      this.p_main=this.tableData[this.p_now-1].main;
      this.score = this.tableData[this.p_now-1].score;
      this.content = this.escapeHTML(this.tableData[this.p_now-1].stuAns);
    },
    async load(){
      const assignmentId = this.assignment && (this.assignment.id || this.assignment.a_id)
      if (!assignmentId) {
        this.$message.warning('未选择作业，请返回课程作业列表后重试')
        this.returnTo()
        return
      }
      try {
        const res = await apiV1.get(`/student/assignments/${assignmentId}`)
        const detail = res.data || {}
        this.assignment.a_name = detail.title
        this.assignment.a_start_time = detail.start_at
        this.assignment.a_end_time = detail.end_at
        this.tableData = (detail.questions || []).map(item => ({
          questionId: item.id,
          porder: item.position,
          main: item.prompt,
          score: item.score,
          stuAns: item.answer || ''
        }))
        this.totalItem = this.tableData.length
        this.total_score = detail.total_score || this.tableData.reduce((sum, item) => sum + item.score, 0)
        this.isDisabled = !this.isBeforeDeadline(detail.end_at)
        if (this.totalItem > 0) {
          // 首次加载只展示数据库中的答案，不能走“切题前保存当前编辑器”逻辑。
          // 此时编辑器仍为空，调用 changeProblem 会把第一题已保存的答案覆盖为空字符串。
          const firstQuestion = this.tableData[0]
          this.p_now = firstQuestion.porder
          this.check()
          this.p_main = firstQuestion.main
          this.score = firstQuestion.score
          this.content = this.escapeHTML(firstQuestion.stuAns)
        } else {
          this.$message.info('该作业暂时没有题目')
        }
      } catch (error) {
        this.$message.error(error.response?.data?.msg || '作业内容加载失败，请稍后重试')
      }
    },
    escapeHTML(content) {
      // 替换除了img标签外的<
      console.log(content)
      if(content === null){
        return content;
      }
      if (content.includes('<p>')) {
        return content;
      }
      let escapedContent = content.replace(/<(?!img)/g, '&lt;');
      // 替换>
      // escapedContent = escapedContent.replace(/>/g, '&gt;');
      // 替换空格为&nbsp;
      // escapedContent = escapedContent.replace(/ /g, '&nbsp;');
      // 替换制表符为&nbsp;&nbsp;&nbsp;&nbsp;（4个空格）
      escapedContent = escapedContent.replace(/\t/g, '&nbsp;&nbsp;&nbsp;&nbsp;');
      // 替换换行符为<br>
      escapedContent = escapedContent.replace(/\n/g, '<br>');
      console.log("escapeHtml:",escapedContent)
      return escapedContent;
    },
    check(){
      if(this.p_now !== 1){
        this.isFirstItem = false
      }
      else if(this.p_now === 1){
        this.isFirstItem = true
      }
      if(this.p_now === this.totalItem){
        this.isLastItem = true
      }
      else if(this.p_now !== this.totalItem){
        this.isLastItem = false
      }
    },
    returnTo(){
      this.$router.push({
        name:'学生课程'
      })
    },
    saveItem(){
      console.log(this.formatContent(this.content))
      this.tableData[this.p_now-1].stuAns = this.formatContent(this.content);
      this.p_now = this.p_now + 1;
      this.check()
      this.p_main=this.tableData[this.p_now-1].main;
      this.score = this.tableData[this.p_now-1].score;
      this.content = this.escapeHTML(this.tableData[this.p_now-1].stuAns);
    },
    lastItem(){
      this.tableData[this.p_now-1].stuAns = this.formatContent(this.content);
      this.p_now = this.p_now - 1;
      this.check()
      this.p_main=this.tableData[this.p_now-1].main;
      this.score = this.tableData[this.p_now-1].score;
      this.content = this.escapeHTML(this.tableData[this.p_now-1].stuAns);
    },
    formatContent(html) {
      console.log(html)
      if(html !== null){
        // 将 <br> 标签替换为换行符
        // html = html.replace(/<br\s*\/?>/gi, '\n');
        // 在每个 <p> 标签之间添加回车键符号
        html = html.replace(/<\/p>/gi, '\n');
        // 删除所有的 <p> 标签
        html = html.replace(/<p[^>]*>/gi, '');
        // 删除其他 HTML 标签部分，但排除 <img> 标签
        html = html.replace(/<(?!img\b)[^>]+>/gi, '');
        console.log("html:",html);
        // 解码 HTML 实体
        return html
            .replace(/&lt;/gi, '<')
            .replace(/&gt;/gi, '>')
            .replace(/&amp;/gi, '&')
            .replace(/&quot;/gi, '"')
            .replace(/&apos;/gi, "'")
            .replace(/&nbsp;/gi, ' ')
            .replace(/&cent;/gi, '¢')
            .replace(/&pound;/gi, '£')
            .replace(/&yen;/gi, '¥')
            .replace(/&euro;/gi, '€')
            .replace(/&copy;/gi, '©')
            .replace(/&reg;/gi, '®')
      }
     else{
       return null
      }
    },

//     // 转义 HTML 特殊字符
//     escapeHtml(text) {
//     let map = {
//       '&': '&amp;',
//       '<': '&lt;',
//       '>': '&gt;',
//       '"': '&quot;',
//       "'": '&#039;'
//     };
//
//     return text.replace(/[&<>"']/g, function(m) { return map[m]; });
// },
//     formatTextWithHTML(text) {
//       // 转义特殊字符 '<'
//       text = text.replace(/</g, '&lt;');
//
//       // 将文本中的换行符替换为 <br> 标签
//       text = text.replace(/\n/g, '<br>');
//
//       // 匹配图片标签并将其保留
//       text = text.replace(/<img [^>]*src="([^"]+)"[^>]*>/g, '<img src="$1">');
//
//       // 将每个文本段落包裹在 <p> 标签中
//       text = text.split('<br>').map(p => `<p>${p}</p>`).join('');
//
//       return text;
//     },
async submit(num){
      if(!this.isBeforeDeadline(this.assignment.a_end_time)){
        this.$message.warning('超过截止时间，操作无效')
        this.$router.push({
          name:'学生课程'
        })
        return
      }
      // this.content  = new DOMParser().parseFromString(this.content, 'text/xml').body.textContent;
    console.log( this.formatContent(this.content))
    this.buttonDis = true;
    this.tableData[this.p_now-1].stuAns = this.formatContent(this.content);
      const assignmentId = this.assignment.id || this.assignment.a_id
      const payload = {
        answers: this.tableData.map(item => ({
          question_id: item.questionId,
          content: item.stuAns || ''
        }))
      }

      try {
        if (num === 1) {
          await apiV1.post(`/student/assignments/${assignmentId}/submit`, payload)
          this.$message.success('提交成功')
          this.returnTo()
        } else {
          await apiV1.put(`/student/assignments/${assignmentId}/submission`, payload)
          this.$message.success('保存成功')
        }
      } catch (error) {
        this.$message.error(error.response?.data?.msg || (num === 1 ? '提交失败' : '保存失败'))
      } finally {
        // 保存只是生成当前答案快照，之后仍可继续修改和正式提交。
        this.buttonDis = false
      }
    }
  }
}
</script>

<style scoped>
::v-deep .ql-container {
  min-height: 200px;
  font-size: medium;
}
.activeButton {
  background-color: #409EFF; /* 设置当前激活按钮的背景色为蓝色 */
}
.answer-sheet {
  padding: 30px;
  overflow-x: hidden;
}

.sheet-inside {
  border: 2px solid #E4EDF8;
  overflow-y: auto;
  height: 72vh; /* 设置容器高度为自适应 */
  padding: 20px;
}

.problem-title p {
  overflow-wrap: break-word;
  /* 或者使用 word-wrap: break-word; */
}
.content {
  padding-left: 10px;
  padding-right: 10px;
}


</style>
