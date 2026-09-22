<template>
  <div class="layout-container">
    <!-- 头部部分 -->
    <div>
      <el-container>
        <el-container>
          <el-main>
            <div>
              <div class="title-container">
                <span class="title">作业-001</span>
                <router-link class="router" to="/student_course">返回</router-link>
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

            <div v-for="grade in grades" :key="grade.id" class="box-container">
              <div  style="margin-top: 10px; margin-left: 1000px; color: #979797;">
                成绩：<span style="color: red; font-size: 20px; font-weight: bolder;">{{ grade.as_score }}</span>
              </div>
              <div style="margin-top: 10px; display: flex;">
                <p>题干：</p> &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;
                <div class="custom-box1">{{ grade.p_main }}</div>
              </div>
              <div style="margin-top: 30px; display: flex;">
                <p>正确答案：</p>
                <div class="custom-box1">{{ grade.p_answer }}</div>
              </div>
              <div style="margin-top: 30px; display: flex;">
                <p>学生答案：</p>
                <div class="custom-box1">{{ grade.as_main }}</div>
              </div>
              <div style="margin-top: 30px; display: flex;">
                <p>LLM批语：</p>
                <div class="custom-box1">{{ grade.llm_check }}</div>
              </div>
              <div style="margin-top: 30px; display: flex;">
                <p>教师批语：</p>
                <div class="custom-box1">{{ grade.t_check }}</div>
              </div>
            </div>
          </el-main>
        </el-container>
      </el-container>
    </div>
  </div>
</template>

<script>

export default {
  data() {
    return {
      students: [
        { s_id: '202103340310', s_name: 'fyl' }
      ],
      total_sheet:[{id:'1',ts_score:'98'}],
      grades: [
        {
          as_score:'10',p_main:'冒泡排序',p_answer:'正确答案',as_main:'学生答案',llm_check:'chat答案',t_check:'教师批语'
        },
        {
          as_score:'10',p_main:'冒泡排序',p_answer:'正确答案',as_main:'学生答案',llm_check:'chat答案',t_check:'教师批语'
        },
        {
          as_score:'10',p_main:'冒泡排序',p_answer:'正确答案',as_main:'学生答案',llm_check:'chat答案',t_check:'教师批语'
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
.router{
  text-decoration: none; /* 去掉下划线 */
  color: #0177FBFF; /* 保持默认文字颜色 */
  cursor: pointer; /* 添加手型光标 */
  font-size: 13px;
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