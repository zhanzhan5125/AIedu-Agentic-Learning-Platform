<template>
        <!-- 这里放置你的主要内容 -->
        <main>
          <div class="course-list">
            <div class="search-create">
              <div class="left-text">我教的课</div>
              <el-input
                  placeholder="搜索课程..."
                  v-model="courseSearch"
                  clearable
                  class="search-input"
              >
                <el-button slot="append" icon="el-icon-search" @click="load()"></el-button>
              </el-input>
              <el-button type="primary" icon="el-icon-plus" @click="openCreateCourseDialog()" class="create-course-btn">开设课程</el-button>
              <el-dialog :visible.sync="dialogVisible" title="开设课程"  width="25%" >
                <!-- 表单内容 -->
                <el-form :model="courseForm"  :rules="rules" label-width="80px" ref="courseForm">
                  <el-form-item prop="cNo" label="选择课程" required>
                    <el-select v-model="courseForm.cNo" placeholder="请选择" style="width: 100%">
                      <el-option
                          v-for="item in optionCourse"
                          :key="item.value"
                          :label="item.label"
                          :value="item.value">
                      </el-option>
                    </el-select>
                  </el-form-item>
                  <el-form-item prop="year" label="开设学年" required>
                    <el-select v-model="courseForm.year" placeholder="请选择" style="width: 100%">
                      <el-option
                          v-for="item in optionsYear"
                          :key="item.value"
                          :label="item.label"
                          :value="item.value">
                      </el-option>
                    </el-select>
                  </el-form-item>
                  <el-form-item prop="term" label="开设学期" required>
                    <el-select v-model="courseForm.term" placeholder="请选择" style="width: 100%">
                      <el-option
                          v-for="item in optionsTerm"
                          :key="item.value"
                          :label="item.label"
                          :value="item.value">
                      </el-option>
                    </el-select>
                  </el-form-item>
                  <el-form-item prop="sectionCode" label="教学班号" required>
                    <el-input v-model.trim="courseForm.sectionCode" maxlength="32" placeholder="例如：01"></el-input>
                  </el-form-item>
                  <el-form-item prop="sectionName" label="教学班名">
                    <el-input v-model.trim="courseForm.sectionName" maxlength="100" placeholder="留空则使用“教学班+编号”"></el-input>
                  </el-form-item>

                  <!-- 其他表单项... -->

                  <el-form-item>
                    <div style="float: right">
                    <el-button type="primary" @click="createCourse()">创建</el-button>
                    <el-button @click="closeCreateCourseDialog()">取消</el-button></div>
                  </el-form-item>
                </el-form>
              </el-dialog>
            </div>
            <div style="margin-bottom: 20px">
            <el-divider></el-divider></div>
            <div class="course-cards">
              <div v-for="course in courses" :key="course.offeringId || course.courseCode" class="course-card">
                <el-button class="course-card-button" @click="gotoCourse(course)">
                  <div class="course-content">
                <img src="../views/img/封面.jpg" alt="Course Image" class="course-cover">
                <div class="course-details">
                  <div class="course-title">{{ course.title }}</div>
                  <div class="course-info">
                    <div>授课教师：{{ course.teacher }}</div>
                    <div>课程编号：{{ course.cno }}</div>
                    <div>教学班：{{ course.sectionCode || '01' }}</div>
                    <div>学年：{{ course.year }}-{{ course.year +1 }}({{course.term}})</div>
                  </div>
                </div></div>
                </el-button>
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
      courseSearch:null,
      currentUser:null,
      // image:'https://placekitten.com/883/355',
      courses: [],
      dialogVisible: false,
      courseForm: {
        cNo: null,
        teacherId: null, // 默认为自己，提取工号
        year:null,
        term:null,
        sectionCode:'01',
        sectionName:''
        // 其他表单项...
      },
      optionCourse:[{
        label:"程序设计C",
        value:'C01'
      },
        {
          label:"JAVA程序设计基础",
          value:'C02'
        },
        {
          label:"python深度学习",
          value:'C03'
        },
      ],
      optionsYear: [
        { label: '2023-2024', value: 2023 },
        { label: '2024-2025', value: 2024 },
        { label: '2025-2026', value: 2025 },
        { label: '2026-2027', value: 2026 },
        { label: '2027-2028', value: 2027 }
      ],

      optionsTerm: [
        { label: '第一学期', value: 1 },
        { label: '第二学期', value: 2 }
      ],
      rules: {
        cNo: [
          {required: true, message: '请选择开设课程', trigger: 'change'}
        ],
        year: [
          {required: true, message: '请选择开设学年', trigger: 'change'}
        ],
        term: [
          { required: true, message: '请选择开设学期', trigger: 'change' },
        ],
        sectionCode: [
          { required: true, message: '请输入教学班编号', trigger: 'blur' },
          { pattern: /^[A-Za-z0-9_-]+$/, message: '教学班编号只能包含字母、数字、下划线或短横线', trigger: 'blur' }
        ]
      }
    };
  },
  created() {
    this.load()
  },
  methods:{
    async load() {
      this.currentUser = this.$store.getters.getUser;
      try {
        const res = await apiV1.get('/teacher/offerings')
        const keyword = (this.courseSearch || '').trim().toLowerCase()
        this.courses = ((res.data && res.data.records) || [])
          .filter(course => !keyword || course.title.toLowerCase().includes(keyword) ||
            course.number.toLowerCase().includes(keyword))
          .map(course => ({
            ...course,
            cno: course.number,
            teacher: this.currentUser.name,
            sectionCode: course.section_code,
            sectionName: course.section_name,
            offeringId: course.id
          }))
      } catch (error) {
        this.courses = []
        this.$message.error(error.response?.data?.msg || '课程列表加载失败，请稍后重试')
      }
    },

    openCreateCourseDialog() {
      this.dialogVisible = true;
      this.beforeCreate()
    },
    async beforeCreate(){
      try {
        const res = await apiV1.get('/teacher/course-catalog')
        this.optionCourse = ((res.data && res.data.records) || []).map(course => ({
          label: `${course.number} ${course.name}`,
          value: course.id
        }))
      } catch (error) {
        this.optionCourse = []
        this.$message.error(error.response?.data?.msg || '课程目录加载失败')
      }
    },
    closeCreateCourseDialog() {
      this.dialogVisible = false;
    },
    createCourse() {
      this.$refs['courseForm'].validate(async (valid) => {
        if(valid){
          try {
            await apiV1.post('/teacher/offerings', {
              course_id: this.courseForm.cNo,
              year: this.courseForm.year,
              term: this.courseForm.term,
              section_code: this.courseForm.sectionCode,
              section_name: this.courseForm.sectionName || null
            })
            this.$message.success('保存成功')
            this.closeCreateCourseDialog()
            await this.load()
          } catch (error) {
            this.$message.error(error.response?.data?.msg || '保存失败')
          }
        }
      })
    },
    gotoCourse(course){
      const courseTemp = {
        ...course,
        title: course.title,
        tittle: course.title,
        courseNumber: course.cno,
        offeringId: course.id || course.offeringId || course.courseCode,
        courseCode: course.id || course.offeringId || course.courseCode
      }
      this.$store.dispatch('setCourse',courseTemp)
      const params = {tittle:course.title};
      this.$router.push({
        name:'课程',
        params:params })
    },
  }
};
</script>

<style>


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
  background-color:#F1F3F5;
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
  margin-right: 20px;

  /* 可根据需要调整右边距 */
}

.search-input{
  width: 200px; /* 设置输入框宽度 */
}
</style>
