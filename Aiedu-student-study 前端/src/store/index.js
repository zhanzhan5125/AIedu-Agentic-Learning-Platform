import Vue from 'vue'
import Vuex from 'vuex'
import apiV1 from '@/utils/apiV1'

Vue.use(Vuex)

let unreadSocket = null
let unreadFallbackTimer = null
let unreadSyncStarted = false

function unreadKey(offeringId) {
  return offeringId ? String(offeringId) : 'global'
}

const store = new Vuex.Store({
  state: {
    currentAssignment:JSON.parse(localStorage.getItem('currentAssignment')) || null,
    user:JSON.parse(localStorage.getItem('user')) || null,
    course:JSON.parse(localStorage.getItem('course')) || null,
    student:JSON.parse(localStorage.getItem('student')) || null,
    stuList:JSON.parse(localStorage.getItem('stuList')) || null,
    summary:JSON.parse(localStorage.getItem('summary')) || 0,
    unreadByScope: {},
    unreadSocketConnected: false,
    pagination: {
      pageNum: 1,
      pageSize: 8,
    },
    sortParams: {//默认按照提交时间降序排列
      sortField: 'submitTime',
      sortOrder: 'descending',
    },
  },
  mutations: {
    setCurrentAssignment(state,param){
      state.currentAssignment = param;
      localStorage.setItem('currentAssignment',JSON.stringify(param));
    },
    clearCurrentAssignment(state) {
      console.log('Clearing current assignment...');
      state.currentAssignment = null;
      localStorage.removeItem('currentAssignment');
    },
    setUser(state, payload) {
      state.user = payload;
      localStorage.setItem('user',JSON.stringify(payload));
    },
    clearUser(state){
      console.log('Clearing current user...');
      state.user = null;
      localStorage.removeItem('user');
    },
    setCourse(state, payload) {
      state.course = payload;
      localStorage.setItem('course',JSON.stringify(payload));
    },
    clearCourse(state){
      console.log('Clearing current course...');
      state.course = null;
      localStorage.removeItem('course');
    },
    setStudent(state, payload) {
      state.student = payload;
      localStorage.setItem('student',JSON.stringify(payload));
    },
    clearStudent(state){
      console.log('Clearing current student...');
      state.student = null;
      localStorage.removeItem('student');
    },
    setStuList(state, payload) {
      state.stuList = payload;
      localStorage.setItem('stuList',JSON.stringify(payload));
    },
    clearStuList(state){
      console.log('Clearing current stuList...');
      state.stuList = null;
      localStorage.removeItem('stuList');
    },
    setPageNum(state, pageNum) {
      state.pagination.pageNum = pageNum;
    },
    setPageSize(state, pageSize) {
      state.pagination.pageSize = pageSize;
    },
    setSortField(state, sortField) {
      state.sortParams.sortField = sortField;
    },
    setSortOrder(state, sortOrder) {
      state.sortParams.sortOrder = sortOrder;
    },
    setSummary(state, payload) {
      state.summary = payload;
      localStorage.setItem('summary',JSON.stringify(payload));
    },
    setUnreadSummary(state, { offeringId, summary }) {
      Vue.set(state.unreadByScope, unreadKey(offeringId), summary || { total: 0 })
    },
    setUnreadSocketConnected(state, connected) {
      state.unreadSocketConnected = connected
    },
  },
  actions: {
    setCurrentAssignment({ commit }, param) {
      commit('setCurrentAssignment', param);
    },
    setUser({ commit }, user) {
      // 在登录时调用这个 action，并传递用户信息
      commit('setUser', user);
    },
    setCourse({ commit }, course) {
      // 在登录时调用这个 action，并传递用户信息
      commit('setCourse', course);
    },
    setStudent({ commit }, student) {
      // 在登录时调用这个 action，并传递用户信息
      commit('setStudent', student);
    },
    setStuList({ commit }, stuList) {
      // 在登录时调用这个 action，并传递用户信息
      commit('setStuList', stuList);
    },
    updatePageInfo({ commit }, { pageNum, pageSize }) {
      commit('setPageNum', pageNum);
      commit('setPageSize', pageSize);
    },
    updateSortParams({ commit }, { sortField, sortOrder }) {
      commit('setSortField', sortField);
      commit('setSortOrder', sortOrder);
    },
    setSummary({ commit }, summary) {
      // 在登录时调用这个 action，并传递用户信息
      commit('setSummary', summary);
    },
    async loadUnread({ commit }, offeringId = null) {
      try {
        const params = offeringId ? { offering_id: offeringId } : {}
        const response = await apiV1.get('/messages/unread-summary', { params })
        commit('setUnreadSummary', { offeringId, summary: response.data || { total: 0 } })
      } catch (_) {
        commit('setUnreadSummary', { offeringId, summary: { total: 0 } })
      }
    },
    ensureUnreadSync({ commit, dispatch, state }, offeringId = null) {
      dispatch('loadUnread', offeringId)
      if (unreadSyncStarted) return
      unreadSyncStarted = true
      const connect = () => {
        const user = JSON.parse(localStorage.getItem('user') || 'null')
        if (!user || !user.token) return
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
        const endpoint = process.env.NODE_ENV === 'development'
          ? `${protocol}//${window.location.hostname}:9091/api/v1/ws/messages`
          : `${protocol}//${window.location.host}/api/v1/ws/messages`
        unreadSocket = new WebSocket(`${endpoint}?token=${encodeURIComponent(user.token)}`)
        unreadSocket.onopen = () => {
          commit('setUnreadSocketConnected', true)
          if (unreadFallbackTimer) clearInterval(unreadFallbackTimer)
          unreadFallbackTimer = null
        }
        unreadSocket.onmessage = event => {
          let payload = {}
          try { payload = JSON.parse(event.data || '{}') } catch (_) {}
          dispatch('loadUnread', null)
          if (payload.offering_id) dispatch('loadUnread', payload.offering_id)
        }
        unreadSocket.onclose = () => {
          commit('setUnreadSocketConnected', false)
          if (!unreadFallbackTimer) {
            unreadFallbackTimer = setInterval(() => {
              dispatch('loadUnread', null)
              Object.keys(state.unreadByScope).filter(key => key !== 'global')
                .forEach(key => dispatch('loadUnread', Number(key)))
            }, 60000)
          }
        }
        unreadSocket.onerror = () => unreadSocket && unreadSocket.close()
      }
      connect()
      window.addEventListener('message-unread-changed', () => {
        dispatch('loadUnread', null)
        if (offeringId) dispatch('loadUnread', offeringId)
      })
    },
  },
  getters: {
    // 获取 menuParam 的值
    getCurrentAssignment: state => state.currentAssignment,
    getUser:(state)=> state.user,
    getCourse:(state) => state.course,
    getStudent:(state) => state.student,
    getStuList:(state) => state.stuList,
    getPageInfo:(state)=>state.pagination,
    getSortParams:(state)=>state.sortParams,
    getSummary:(state)=>state.summary,
    getUnreadTotal: state => offeringId => Number((state.unreadByScope[unreadKey(offeringId)] || {}).total || 0)
  },
})
export default store
