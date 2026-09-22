import Vue from 'vue'
import VueRouter from 'vue-router'
import HomeView from '../views/ManageTeacher.vue'
import store from "@/store";

Vue.use(VueRouter)

const routes = [
  {
    path: '/',
    component: ()=>import('../views/ManageTeacher.vue'),
    redirect:"/login",
    children:[
      // { path: 'course', name: '课程', component: () => import('../views/Course.vue')},
      { path: 'home', name: '主页', meta: { roles: ['teacher'] }, component: () => import('../views/Home.vue')},
      { path: 'message', name: '消息', meta: { roles: ['teacher'], messageScope: 'aggregate' }, component: () => import('../views/MessagingCenter.vue')},
      { path: 'teacher_inbox', name: '教师收件箱', meta: { roles: ['teacher'], title: '收件箱' }, component: () => import('../views/FeaturePlaceholder.vue')},
      { path: 'teacher_cloud', name: '教师云盘', meta: { roles: ['teacher'], title: '云盘与资料' }, component: () => import('../views/FeaturePlaceholder.vue')},
    ]
  },
  {
    path: '/',
    component: ()=>import('../views/ManageHeader.vue'),
    redirect:"/login",
    children:[
        { path: 'llmcheck', name: '智能批阅', meta: { roles: ['teacher'], teacherCourse: true }, component: () => import('../views/LlmPromptTeacher.vue')},
        { path: 'llmcheck_admin', name: '智能批阅管理', meta: { roles: ['teacher'] }, component: () => import('../views/LlmPromptManager.vue')},
      { path: 'course', name: '课程', meta: { roles: ['teacher'], teacherCourse: true }, component: () => import('../views/Course.vue')},
      { path: 'course_insights', name: '班级学情', meta: { roles: ['teacher'], teacherCourse: true }, component: () => import('../views/LearningInsights.vue')},
      { path: 'course_resources', name: '教师课程资料', meta: { roles: ['teacher'], teacherCourse: true }, component: () => import('../views/CourseResources.vue')},
      { path: 'course_messages', name: '教师课程消息', meta: { roles: ['teacher'], messageScope: 'course', teacherCourse: true }, component: () => import('../views/MessagingCenter.vue')},
      { path: 'agent_studio', name: '多智能体工作台', meta: { roles: ['teacher'], teacherCourse: true }, component: () => import('../views/AgentStudio.vue')},
      { path: 'assignment', name: '作业', meta: { roles: ['teacher'], teacherCourse: true }, component: () => import('../views/Assignment.vue')},
        { path: 'assignment_item', name: '作业题目', meta: { roles: ['teacher'], teacherCourse: true }, component: () => import('../views/AssignmentItem.vue')},
      { path: 'checkassignment', name: '查看作业',  beforeRouteEnter: (to, from, next) => {
          // Retrieve pagination state when entering the page
          store.dispatch('updatePageInfo', {
            pageNum: store.state.pagination.pageNum,
            pageSize: store.state.pagination.pageSize,
          });
              store.dispatch('updateSortParams', {
                  sortField: store.state.sortParams.sortField,
                  sortOrder: store.state.sortParams.sortOrder,
              });
          next();
        }, meta: { roles: ['teacher'], teacherCourse: true }, component: () => import('../views/CheckAssignment.vue')},
      { path: 'manage_stu', name: '课程管理',  beforeRouteEnter: (to, from, next) => {
          // Retrieve pagination state when entering the page
          store.dispatch('updatePageInfo', {
            pageNum: store.state.pagination.pageNum,
            pageSize: store.state.pagination.pageSize,
          });
          next();
        }, meta: { roles: ['teacher'], teacherCourse: true }, component: () => import('../views/Manage_stu.vue')},
      { path: 'manage_ass', name: '作业库',  beforeRouteEnter: (to, from, next) => {
          // Retrieve pagination state when entering the page
          store.dispatch('updatePageInfo', {
            pageNum: store.state.pagination.pageNum,
            pageSize: store.state.pagination.pageSize,
          });
          next();
        }, meta: { roles: ['teacher'], teacherCourse: true }, component: () => import('../views/Manage_ass.vue')},
      { path: 'student_grade', name: '学生成绩', meta: { roles: ['teacher', 'student'], teacherCourse: true }, component: () => import('../views/StudentGrade.vue')},
      { path: 'teacher_mark', name: '教师批阅', meta: { roles: ['teacher'], teacherCourse: true }, component: () => import('../views/TeacherMark.vue')},
      { path: 'teacher_create_assignment', name: '创建作业', meta: { roles: ['teacher'], teacherCourse: true }, component: () => import('../views/TeacherCreateAssignment.vue')},
      { path: 'assignment_detail', name: '作业详情统计', meta: { roles: ['teacher'], teacherCourse: true }, component: () => import('../views/AssignmentDetail.vue')},
      { path: 'no_submitted', name: '未提交学生', meta: { roles: ['teacher'], teacherCourse: true }, component: () => import('../views/NoSubmitted.vue')},
      { path: 'student_answer', name: '学生作答', meta: { roles: ['student'] }, props: (route) => ({ query: route.query }),component: () => import('../views/StudentAnswer.vue')}
    ]
  },
  {
    path: '/',
    component: ()=>import('../views/ManageStudent.vue'),
    redirect:"/login",
    children:[
      // { path: 'course', name: '课程', component: () => import('../views/Course.vue')},
      { path: 'student_home', name: '学生主页', meta: { roles: ['student'] }, component: () => import('../views/StudentHome.vue')},
      { path: 'student_home_messages', name: '学生主页消息', meta: { roles: ['student'], messageScope: 'aggregate' }, component: () => import('../views/MessagingCenter.vue')},
      { path: 'student_inbox', name: '学生收件箱', meta: { roles: ['student'], title: '收件箱' }, component: () => import('../views/FeaturePlaceholder.vue')},
      { path: 'student_home_cloud', name: '学生主页云盘', meta: { roles: ['student'], title: '云盘' }, component: () => import('../views/FeaturePlaceholder.vue')}
    ]
  },
  {
    path: '/',
    component: ()=>import('../views/ManageStudentCourse.vue'),
    redirect:"/login",
    children:[
      // { path: 'course', name: '课程', component: () => import('../views/Course.vue')},
      { path: 'student_course', name: '学生课程', meta: { roles: ['student'] }, props: (route) => ({ query: route.query }),component: () => import('../views/StudentCourse.vue')},
      { path: 'ai_chat', name: '智能问答', meta: { roles: ['student'] }, component: () => import('../views/AIChat.vue')},
      { path: 'student_learning', name: '个人学情', meta: { roles: ['student'] }, component: () => import('../views/LearningInsights.vue')},
      { path: 'student_course_map', name: '课程路线', meta: { roles: ['student'] }, component: () => import('../views/CourseMap.vue')},
      { path: 'student_messages', name: '学生消息', meta: { roles: ['student'], messageScope: 'course' }, component: () => import('../views/MessagingCenter.vue')},
      { path: 'student_resources', name: '课程资料', meta: { roles: ['student'], title: '课程资料' }, component: () => import('../views/CourseResources.vue')}
    ]
  },
  {
    path: '/',
    component: ()=>import('../views/ManageAdmin.vue'),
    redirect:"/login",
    children:[
      // { path: 'course', name: '课程', component: () => import('../views/Course.vue')},
      { path: 'admin_home',  beforeRouteEnter: (to, from, next) => {
          // Retrieve pagination state when entering the page
          store.dispatch('updatePageInfo', {
            pageNum: store.state.pagination.pageNum,
            pageSize: store.state.pagination.pageSize,
          });
          next();
        },name: '管理员首页', meta: { roles: ['admin'] }, props: (route) => ({ query: route.query }),component: () => import('../views/AdminHome.vue')},
      { path: 'admin_check_schedule', beforeRouteEnter: (to, from, next) => {
          // Retrieve pagination state when entering the page
          store.dispatch('updatePageInfo', {
            pageNum: store.state.pagination.pageNum,
            pageSize: store.state.pagination.pageSize,
          });
          next();
        }, name: '排课情况', meta: { roles: ['admin'] }, props: (route) => ({ query: route.query }),component: () => import('../views/AdminCheckSchedule.vue')},
      { path: 'admin_teacher',  beforeRouteEnter: (to, from, next) => {
          // Retrieve pagination state when entering the page
          store.dispatch('updatePageInfo', {
            pageNum: store.state.pagination.pageNum,
            pageSize: store.state.pagination.pageSize,
          });
          next();
        },name: '教师管理', meta: { roles: ['admin'] }, props: (route) => ({ query: route.query }),component: () => import('../views/AdminTeacher.vue')},
      { path: 'admin_student',  beforeRouteEnter: (to, from, next) => {
          // Retrieve pagination state when entering the page
          store.dispatch('updatePageInfo', {
            pageNum: store.state.pagination.pageNum,
            pageSize: store.state.pagination.pageSize,
          });
          next();
        },name: '学生管理', meta: { roles: ['admin'] }, props: (route) => ({ query: route.query }),component: () => import('../views/AdminStudent.vue')},
    ]
  },
  {
    path: '/login',
    name: 'Login',
    component: () => import('../views/Login.vue'),
    meta: { public: true }
  },
  // {
  //   path: '/checkassignment',
  //   name: '查看作业',
  //   // component: YourAssignmentComponent,
  //   beforeRouteEnter: (to, from, next) => {
  //     // Retrieve pagination state when entering the page
  //     store.dispatch('updatePageInfo', {
  //       pageNum: store.state.pagination.pageNum,
  //       pageSize: store.state.pagination.pageSize,
  //     });
  //     next();
  //   },
  // },
  // {
  //   path: '/admin_check_schedule',
  //   name: '排课情况',
  //   // component: YourAssignmentComponent,
  //   beforeRouteEnter: (to, from, next) => {
  //     // Retrieve pagination state when entering the page
  //     store.dispatch('updatePageInfo', {
  //       pageNum: store.state.pagination.pageNum,
  //       pageSize: store.state.pagination.pageSize,
  //     });
  //     next();
  //   },
  // },
  // {
  //   path: '/admin_home',
  //   name: '管理员首页',
  //   // component: YourAssignmentComponent,
  //   beforeRouteEnter: (to, from, next) => {
  //     // Retrieve pagination state when entering the page
  //     store.dispatch('updatePageInfo', {
  //       pageNum: store.state.pagination.pageNum,
  //       pageSize: store.state.pagination.pageSize,
  //     });
  //     next();
  //   },
  // },
  // {
  //   path: '/admin_teacher',
  //   name: '教师管理',
  //   // component: YourAssignmentComponent,
  //   beforeRouteEnter: (to, from, next) => {
  //     // Retrieve pagination state when entering the page
  //     store.dispatch('updatePageInfo', {
  //       pageNum: store.state.pagination.pageNum,
  //       pageSize: store.state.pagination.pageSize,
  //     });
  //     next();
  //   },
  // },
  // {
  //   path: '/admin_student',
  //   name: '学生管理',
  //   // component: YourAssignmentComponent,
  //   beforeRouteEnter: (to, from, next) => {
  //     // Retrieve pagination state when entering the page
  //     store.dispatch('updatePageInfo', {
  //       pageNum: store.state.pagination.pageNum,
  //       pageSize: store.state.pagination.pageSize,
  //     });
  //     next();
  //   },
  // },
  // {
  //   path: '/manage_stu',
  //   name: '课程管理',
  //   // component: YourAssignmentComponent,
  //   beforeRouteEnter: (to, from, next) => {
  //     // Retrieve pagination state when entering the page
  //     store.dispatch('updatePageInfo', {
  //       pageNum: store.state.pagination.pageNum,
  //       pageSize: store.state.pagination.pageSize,
  //     });
  //     next();
  //   },
  // },
  // {
  //   path: '/manage_ass',
  //   name: '作业库',
  //   // component: YourAssignmentComponent,
  //   beforeRouteEnter: (to, from, next) => {
  //     // Retrieve pagination state when entering the page
  //     store.dispatch('updatePageInfo', {
  //       pageNum: store.state.pagination.pageNum,
  //       pageSize: store.state.pagination.pageSize,
  //     });
  //     next();
  //   },
  // }
]

const router = new VueRouter({
  mode: 'history',
  base: process.env.BASE_URL,
  routes
})
// 路由守卫
// router.beforeEach((to, from, next) => {
//   localStorage.setItem("currentPathName", to.name)  // 设置当前的路由名称，为了在Header组件中去使用
//   store.commit("setPath")  // 触发store的数据更新
//   next()  // 放行路由
// })
export default router
