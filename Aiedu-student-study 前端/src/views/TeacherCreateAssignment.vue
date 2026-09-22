<template>
  <div id="content" class="content" >
  <div class="answer-container" style="display: flex; flex-direction: column;">
    <div class="answer-header"
         style="height: 60px; width: 100%; border-bottom: 3px solid #ccc; display: flex; justify-content: space-between;">
      <div class="left-side" style="height: 100%;margin-left:40px">
        <div class="left-upper" style="display: flex; font-size: 18px; margin-top: 15px;">
          <p>标题：</p>
          <el-input v-model="tittle" placeholder="请输入内容" style="width: 200px;"></el-input>
        </div>
      </div>
      <div class="right-side" style="height: 100%; line-height: 57px;margin-right:20px">
        <el-button type="success" style="width:100px;margin-right:10px" round @click="openDialog()" :disabled="hasAssigned" >智能题目生成</el-button>
        <el-button type="primary" style="width:100px;margin-right:50px" round @click="saveToDatabase()">保存并返回</el-button>
      </div>
    </div>

    <div class="answer-bottom" style="height:100%;width:100%;display:flex">
      <div class="answer-aside" style="width:300px;background-color: #EAF4FD;border-right: 1px solid #ccc;">
        <div class="block" style="width:100%;height:20px;background-color: #EAF4FD"></div>
        <div style="display: flex; align-items: center;">
          <p style="color: #979797; margin-left: 10px; margin-right: 20px;">题数:{{ item }}</p>
          <p style="color: #979797; margin-left: 20px; margin-right: 20px;">总分:{{ this.totalscore }}</p>
        </div>
        <div>
          <div style="margin: 10px; font-size: 20px;">
            <div style="margin-bottom: 20px">题目列表<el-button :disabled="hasAssigned" type="primary" @click="addItem" icon="el-icon-circle-plus" round style="margin-left: 80px">添加题目</el-button></div>
            <div v-for="item in itemtable">
              <div style="display: flex; align-items: center;justify-content: space-between; margin-left: 10px;width:100% ">
                <el-button class="text-group" style="width: 60%;padding: 10px;margin-bottom: 10px" @click="gotoItem(item.item_order)" >
                  <div type="info" style="font-size: 16px;">{{ item.item_order }}.{{ item.item_type }} ({{ item.item_score }}分)</div>
                </el-button>
                <div  class="button-group" style="margin-right:20px">
                  <el-button @click="moveUp(item.item_order)" type="text" :style="{ fontSize: '20px' }"
                             icon="el-icon-caret-top" :disabled="hasAssigned"></el-button>
                  <el-button @click="moveDown(item.item_order)" type="text" :style="{ fontSize: '20px' }"
                             icon="el-icon-caret-bottom" :disabled="hasAssigned"></el-button>
                  <el-button @click="clear(item.item_order)" type="text" :style="{ fontSize: '20px' }"
                             icon="el-icon-delete" :disabled="hasAssigned"></el-button>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
      <div class="box-container" >
        <el-form :model="form" ref="form" label-width="80px" size="medium">
          <el-form-item label="题型" style="margin-top: 20px">
            <el-radio-group v-model="form.type" :disabled="disabled">
              <el-radio :label="1">简答题</el-radio>
              <el-radio :label="2">单选题</el-radio>
              <el-radio :label="3">多选题</el-radio>
              <el-radio :label="4">判断题</el-radio>
            </el-radio-group>
          </el-form-item>
          <el-form-item label="分数">
            <el-input-number :disabled="disabled || hasAssigned"  v-model="form.score" placeholder="请输入分数" style="width: 150px;"></el-input-number>
          </el-form-item>
          <el-form-item label="题干">
            <el-input :disabled="disabled" type="textarea" :rows="10" placeholder="请输入内容" v-model="form.main" style="width: 1000px;color:#000000;font-size: large"
                      @keydown.tab.native="tabInput_main($event)"></el-input>
          </el-form-item>
          <el-form-item label="答案">
            <el-input :disabled="disabled" type="textarea" :rows="10" v-model="form.answer" style="width: 1000px;font-size: large" @keydown.tab.native="tabInput_answer($event)"></el-input>
          </el-form-item>
          <el-form-item>
            <el-button :disabled="disabled" type="primary" round style="width:140px;margin-left:400px" @click="saveItem()">保存</el-button>
            <el-button :disabled="disabled" type="primary" round style="width:140px;margin-right:15px" @click="clearInput()">重置</el-button>
          </el-form-item>
        </el-form>
      </div>

    </div>
  </div>
    <el-dialog
        title="智能题目生成"
        :visible="dialogVisible"
        :modal="true"
        @close="closeDialog"
        :closeOnClickModal="false"
        width="30%"
        :disabled="hasAssigned"
    >
      <div style="overflow-y: auto; display: flex; flex-direction: column;"  v-loading="this.loading"
           element-loading-text="题目生成中">
        <div style="display: flex; flex-direction: row; align-items: center;">
          <div style="margin-left:10px; display:inline; background-color: #e3effc; color: #409dfd; border-radius: 3px; padding: 3px; font-size: medium; width: 20%; text-align: center; justify-content: center">
            &nbsp;关键词&nbsp;
          </div>
          <div style="width: 50%; margin-left: 10px; margin-right: 10px;">
            <el-input
                size="large"
                style="height: 40px"
                prefix-icon="el-icon-key"
                v-model="currentKeyword"
                placeholder="请输入关键词"
                required
            ></el-input>
          </div>
          <el-button @click="addKeyword" type="primary">添加</el-button>
        </div>
        <div style="margin-top: 10px;margin-left: 10px">
          <el-tag
              v-for="(keyword, index) in keywords"
              :key="index"
              type="success"
              closable
              @close="removeKeyword(index)"
              style="margin-right: 10px"
              size="medium "
          >{{ keyword }}</el-tag>
        </div>
        <div style="display: flex; flex-direction: row; align-items: center;margin-top: 10px">
          <div style="margin-left:10px; display:inline; background-color: #e3effc; color: #409dfd; border-radius: 3px; padding: 3px; font-size: medium; width: 20%; text-align: center; justify-content: center">
            &nbsp;题目数量&nbsp;
          </div>
          <div style="width: 50%; margin-left: 10px; margin-right: 10px;">
            <el-input-number v-model="itemNum" placeholder="请输入题目数量" size="medium"  :min="0"></el-input-number>
          </div>
        </div>
        <div style="display: flex; flex-direction: row; align-items: center;margin-top: 20px">
          <div style="margin-left:10px; display:inline; background-color: #e3effc; color: #409dfd; border-radius: 3px; padding: 3px; font-size: medium; width: 20%; text-align: center; justify-content: center">
            &nbsp;题目难度&nbsp;
          </div>
          <div style="width: 50%; margin-left: 10px; margin-right: 10px;">
            <el-select v-model="itemLevel" placeholder="请选择题目难度" size="medium" >
              <el-option
                  v-for="item in optionsLevel"
                  :key="item.value"
                  :label="item.label"
                  :value="item.value">
              </el-option>
            </el-select>
          </div>
        </div>
        <div style="display: flex; flex-direction: row; align-items: center;justify-content:center;margin-top: 20px;gap: 20px">
          <el-button type="primary"  size="medium" @click="create">生成</el-button>
          <el-button type="info" size="medium" @click="reset">重置</el-button>
        </div>
        <div style="color: #888888; font-size: 12px; text-align: center;margin-top: 20px">大语言模型自动生成，可能会产生错误，请做检查</div>

      </div>
    </el-dialog>



  </div>
</template>


<script>
import apiV1 from '@/utils/apiV1'
export default {
  name: "Answer",
  data() {
    return {
      currentOrder:0,
      user:null,
      course:null,
      assignment:null,
      tittle:'',
      item: 0,  // Make sure "item" is defined in your data
      totalscore: 0,
      itemtable: [],
      form: {
        type:'',
        score:0,
        main:'',
        answer:'',
        windowWidth: window.innerWidth,
        windowHeight: window.innerHeight,
      },
      dialogVisible:false,
      currentKeyword: '',
      keywords: [],
      itemNum:0,
      itemLevel:null,
      optionsLevel:[
        { label: '简单', value: 0 },
        { label: '适中', value: 1 },
        { label: '困难', value: 2 }      ],
      loading:false,
      disabled:false,
      hasAssigned:false
    };
  },
  created() {
    this.user = this.$store.getters.getUser
    this.course = this.$store.getters.getCourse
    this.load()
  },
  watch: {
    // 监听题干输入框的变化
    'form.main': function(newVal) {
      // 在输入框内容发生变化时，将新值保存到相应的绑定值中
      this.form.main = newVal;
      this.saveItem();
    },
    // 监听答案输入框的变化
    'form.answer': function(newVal) {
      // 在输入框内容发生变化时，将新值保存到相应的绑定值中
      this.form.answer = newVal;
      this.saveItem();
    },
  },
  methods: {
    load(){
        console.log("加载函数")
        this.assignment = this.$store.getters.getCurrentAssignment
      console.log("开始时间",this.assignment.a_start_time)
      if(this.assignment.a_start_time){
        this.hasAssigned = true
      }
        this.tittle = this.assignment.a_name
        apiV1.get(`/teacher/assignments/${this.assignment.a_id}`).then(res => {
          if(res.data && res.data.questions){
            const typeNames={short_answer:'简答题',single_choice:'单选题',multiple_choice:'多选题',programming:'编程题'}
            this.itemtable=res.data.questions.map(question=>({item_order:question.position,item_type:typeNames[question.kind]||'简答题',item_score:question.score,item_main:question.prompt,item_answer:question.reference_answer||'',difficulty:question.difficulty}))
            this.item=this.itemtable.length
            this.gotoItem(1)
          }
          if(this.item === 0){
            this.disabled = true
          }
          let totalScore=0
          for(let i=0;i<this.item;i++){
            totalScore+=this.itemtable[i].item_score
          }
          this.totalscore=totalScore
          console.log("score:",totalScore)
          console.log(res)
          if(this.item !== 0){
            this.gotoItem(1)
          }
        })
    },
    clear(order){
      const index = order - 1;
      this.item = this.item - 1
      this.totalscore =this.totalscore - this.itemtable[index].item_score
      if (index >= 0 && index < this.itemtable.length) {
        // 删除指定索引的题目
        this.itemtable.splice(index, 1);
        // 更新后续题目的 item_order
        for (let i = index; i < this.itemtable.length; i++) {
          this.itemtable[i].item_order -= 1;
        }
      }
      this.clearInput()
    },
    gotoItem(order){
      this.currentOrder = order
      const index = order - 1;
      let typeTemp = this.itemtable[index].item_type
      if(typeTemp === '简答题'){
        this.form.type = 1
      }
      else if(typeTemp === '单选题'){
        this.form.type = 2
      }
      else if( typeTemp === '多选题'){
       this.form.type = 3
      }
      else if(typeTemp === '判断题'){
        this.form.type = 4
      }
      this.form.score = this.itemtable[index].item_score
      this.form.main = this.itemtable[index].item_main
      this.form.answer = this.itemtable[index].item_answer
    },
    gotoManageAss() {
      this.$router.push({
        path: '/manage_ass'
      })
    },
    addItem(){
      this.disabled = false
      this.clearInput()
      this.item ++
      this.currentOrder = this.item
      const newItem = {
        item_order:this.item,
        item_type:1,
        item_score:0,
        item_main:"",
        item_answer:"",
      };
      this.itemtable.push(newItem)
      this.form.type = 1
      this.form.score = this.itemtable[this.item-1].item_score
      this.form.main = this.itemtable[this.item-1].item_main
      this.form.answer = this.itemtable[this.item-1].item_answer
    },
    saveItem(){
      let typeTemp = ''
      if(this.form.type === 1){
        typeTemp = '简答题'
      }
      else if(this.form.type === 2){
        typeTemp = '单选题'
      }
      else if(this.form.type === 3){
        typeTemp = '多选题'
      }
      else if(this.form.type === 4){
        typeTemp = '判断题'
      }
      this.itemtable[this.currentOrder-1].item_type = typeTemp
      this.itemtable[this.currentOrder-1].item_score = this.form.score
      this.itemtable[this.currentOrder-1].item_main = this.form.main
      this.itemtable[this.currentOrder-1].item_answer = this.form.answer
      this.calculateTotalScore()
    },
    calculateTotalScore(){
      let score = 0
      for(let i = 0;i < this.item;i++){
        score += this.itemtable[i].item_score
      }
      this.totalscore = score
    },
    saveToDatabase() {
      const kinds={'简答题':'short_answer','单选题':'single_choice','多选题':'multiple_choice','判断题':'single_choice','编程题':'programming'}
      const questions=this.itemtable.map(item=>({kind:kinds[item.item_type]||'short_answer',prompt:item.item_main,reference_answer:item.item_answer,score:Number(item.item_score)||0,difficulty:item.difficulty||0}))
      apiV1.put(`/teacher/assignments/${this.assignment.a_id}`,{title:this.tittle,questions}).then(()=>{
        this.$message.success('保存成功')
        this.$router.push({name:'作业库'})
      }).catch(error=>this.$message.error(error.response?.data?.msg||'保存失败'))
    },
    clearInput() {
      // 清空输入框的逻辑
      this.form.type = 1;
      this.form.score = '';
      this.form.main = '';
      this.form.answer = '';
    },

    tabInput_main(e) {
      e.preventDefault()
      const insertText = '\t'
      const elInput = e.target
      const startPos = elInput.selectionStart
      const endPos = elInput.selectionEnd
      if (startPos === undefined || endPos === undefined) return
      const txt = elInput.value
      elInput.value = txt.substring(0, startPos) + insertText + txt.substring(endPos)
      elInput.focus()
      elInput.selectionStart = startPos + insertText.length;
      elInput.selectionEnd = startPos + insertText.length;
      this.form.main = elInput.value
    },
    tabInput_answer(e) {
      e.preventDefault()
      const insertText = '\t'
      const elInput = e.target
      const startPos = elInput.selectionStart
      const endPos = elInput.selectionEnd
      if (startPos === undefined || endPos === undefined) return
      const txt = elInput.value
      elInput.value = txt.substring(0, startPos) + insertText + txt.substring(endPos)
      elInput.focus()
      elInput.selectionStart = startPos + insertText.length;
      elInput.selectionEnd = startPos + insertText.length;
      this.form.answer = elInput.value
    },
    moveUp(index) {
      if (index-1 > 0) {
        // 题目不是第一个才能上移
        this.swapItems(index, index - 1);
      }
    },

    moveDown(index) {
      if (index < this.itemtable.length) {
        // 题目不是最后一个才能下移
        this.swapItems(index, index + 1);
      }
    },
    swapItems(index1, index2) {
      const temp = this.itemtable[index1-1];
      this.$set(this.itemtable, index1-1, this.itemtable[index2-1]);
      this.$set(this.itemtable, index2-1, temp);
      this.itemtable[index1-1].item_order = index1;
      this.itemtable[index2-1].item_order = index2;
    },
    openDialog() {
      this.dialogVisible = true;
    },
    closeDialog() {
      this.dialogVisible = false;
      this.reset();
    },
    addKeyword() {
      if (this.currentKeyword.trim() !== '') {
        this.keywords.push(this.currentKeyword.trim());
        this.currentKeyword = '';
      }
    },
    removeKeyword(index) {
      this.keywords.splice(index, 1);
    },
    async create(){
      this.loading = true
      try{
        const created=await apiV1.post('/ai/question-jobs',{resource_id:this.course.offeringId||this.course.id,idempotency_key:`question-${Date.now()}`,prompt:`关键词：${this.keywords.join('、')}；数量：${this.itemNum}；难度：${this.itemLevel}`})
        let result=null
        for(let attempt=0;attempt<60;attempt++){
          const job=await apiV1.get(`/jobs/${created.data.job_id}`)
          if(job.data.status==='succeeded'){result=job.data.result||{};break}
          if(job.data.status==='failed')throw new Error(job.data.error||'生成失败')
          await new Promise(resolve=>setTimeout(resolve,1000))
        }
        if(!result)throw new Error('生成超时')
        const records=result.questions||[]
        for (let i = 0 ; i < records.length; i++) {
            const item = {
              item_order: this.item + i + 1,
              item_type: "简答题",
              item_score: records[i].score||10,
              item_main: records[i].prompt||records[i].question,
              item_answer: records[i].reference_answer||records[i].answer||'',
              difficulty: records[i].difficulty||this.itemLevel
            };
            this.itemtable.push(item);
        }
        this.$message.success('题目生成成功')
      }catch(error){
        this.$message.error(error.response?.data?.msg||error.message||'题目生成失败')
      }finally{
        this.loading = false
        this.item = this.itemtable.length
        this.closeDialog()
        this.disabled = false
      }
    },
    reset(){
      this.itemNum = 0
      this.itemLevel = null
      this.currentKeyword = ''
      this.keywords = []
    }
    // ... 其他方法 ...
  }
};
</script>

<style scoped>

.content {
  padding-left: 10px;
  padding-right: 10px;
}

.box-container {
  display: flex;
  flex-direction: column;
  align-items: center;
  height: 85vh;
}
</style>
