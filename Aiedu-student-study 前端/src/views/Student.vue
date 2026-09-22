<template>
    <div class="layout-container">
      <!-- 头部部分 -->
      <StuHeaderComponent />
      <div>
        <el-container>
          <el-container>
            <el-main>
              <div>
                <div class="title-container">
                  <span class="title">作业-001</span>
                  <el-link type="primary" class="return-link">返回</el-link>
                </div>
                <hr class="line">
              </div>
  
              <div v-for="student in students" :key="student.id" style="display: flex; align-items: center; margin-bottom: 20px; margin-top: 20px;">
                <div style="color: #979797; margin-left: 5px; margin-right: 10px;">姓名：{{ student.s_name }}</div>
                <div style="color: #979797; margin-left: 10px; margin-right: 10px;">学号：{{ student.s_id }}</div>
                <div v-for="total in total_sheet" :key="total.id" style="display: flex; margin-left: 800px; align-items: baseline;">
                  <p style="color: #979797;">总成绩：</p>
                  <p style="color: red; font-size: 30px; font-weight: bolder; align-self: baseline;">{{ total.ts_score }}</p>
                </div>
              </div>
  
              <div v-for="container in containers" :key="container.id" class="box-container">
                <div v-for="answer in container.answer_sheet" :key="answer.as_id" style="margin-top: 10px; margin-left: 1000px; color: #979797;">
                  成绩：<span style="color: red; font-size: 20px; font-weight: bolder;">{{ answer.as_score }}</span>
                </div>
                <div v-for="problem in container.problem_sheet" :key="problem.p_id" style="margin-top: 10px; display: flex;">
                  <p>题干：</p> &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;
                  <div class="custom-box1">{{ problem.p_id }} {{ problem.p_main }}</div>
                </div>
                <div v-for="problem in container.problem_sheet" :key="problem.p_id" style="margin-top: 30px; display: flex;">
                  <p>正确答案：</p>
                  <div class="custom-box1">{{ problem.p_answer }}</div>
                </div>
                <div v-for="answer in container.answer_sheet" :key="answer.as_id">
                  <div style="margin-top: 30px; display: flex;">
                    <p>学生答案：</p>
                    <div class="custom-box1">{{ answer.as_main }}</div>
                  </div>
                  <div style="margin-top: 30px; display: flex;">
                    <p>LLM批语：</p>
                    <div class="custom-box1">{{ answer.llm_check }}</div>
                  </div>
                  <div style="margin-top: 30px; display: flex;">
                    <p>教师批语：</p>
                    <div class="custom-box1">{{ answer.t_check }}</div>
                  </div>
                </div>
              </div>
  
            </el-main>
          </el-container>
        </el-container>
      </div>
    </div>
  </template>
  
  <script>
  import HeaderComponent from '../components/Header.vue';
  import StuHeaderComponent from '../components/StuHeader.vue';
  
  export default {
  data() {
    return {
      students: [
        { s_id: '202103340310', s_name: 'fyl' }
      ],
      total_sheet:[{id:'1',ts_score:'98'}],
      containers: [
        {
          id: 1,
          answer_sheet: [
            { as_id: 1, as_main: '1111', as_score: '10', t_check: '222', llm_check: '333' },
          ],
          problem_sheet: [
            { p_id: 1, p_main: '1111', p_answer: '111', p_score: "10" },
          ],
        },
        {
          id: 2,
          answer_sheet: [
            { as_id: 2, as_main: '1111', as_score: '9', t_check: '222', llm_check: '333' },
          ],
          problem_sheet: [
            { p_id: 2, p_main: '222', p_answer: '2222', p_score: "10" },
          ],
        }
      ]
    };
  },
};
</script>
  
  
  
  
<style>
.title {
    display: block;
    font-size: 18px;
    color: black;
    font-weight: bold;

}

.line {
    flex: 1;
    /* 让横线占据剩余的空间 */
    border-top: 2px solid #d8d8d8;
    /* 设置横线样式 */
    margin-top: 5px;
    /* 调整横线与标题之间的间距 */
    height: 1px;
}

.search-button-container {
    display: flex;
    margin-bottom: 20px;
}

.button-container {
    display: flex;

}

.search-input {
    width: 250px;
    /* 设置输入框宽度 */
}

.title-container {
    display: flex;
    justify-content: space-between;
    align-items: center;
}

.table-container {
    display: flex;
    justify-content: center;
    align-items: center;
}

.custom-box1 {
    width: 1000px;
    height: 80px;
    border: 1px solid #EBEEF5;
    padding: 20px;

}

.box-container {
    display: flex;
    flex-direction: column;
    border: 2px solid #DCDFE6;
    padding: 20px;
    margin-top: 0;

}
</style>