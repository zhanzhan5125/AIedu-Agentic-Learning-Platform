<template>
  <div class="page-shell">
    <div class="page-heading"><h2>课程多智能体工作台</h2><p>四个业务智能体按边界协作；所有计划、工具调用、委派和校验均可追溯。</p></div>
    <el-tabs v-model="activeTab">
      <el-tab-pane label="出题智能体" name="assignment">
        <el-row :gutter="16" class="assignment-workspace">
          <el-col :span="7"><el-card><div slot="header">生成新草稿</div>
            <el-form label-position="top">
              <el-form-item label="关键词"><el-input v-model="keywords" placeholder="例如：递归、二叉树、复杂度" /></el-form-item>
              <el-form-item label="按已发布课程路线选择章节">
                <el-checkbox-group v-if="publishedChapters.length" v-model="selectedChapterIds" class="chapter-selector">
                  <div v-for="chapter in publishedChapters" :key="chapter.id" class="assignment-chapter">
                    <el-checkbox :label="chapter.id">
                      <b>{{ chapter.name }}</b><small>{{ chapter.children.length }} 个知识点</small>
                    </el-checkbox>
                    <div v-if="chapter.children.length" class="assignment-points">
                      <span v-for="point in chapter.children" :key="point.id || point.node_key">
                        {{ point.name }}
                      </span>
                    </div>
                    <div v-else class="assignment-points empty">该章节暂未关联知识点</div>
                  </div>
                </el-checkbox-group>
                <el-alert v-else title="发布课程路线后，可按章节约束出题范围" type="info" :closable="false" show-icon />
              </el-form-item>
              <el-form-item label="题型（可多选）">
                <el-checkbox-group v-model="questionKinds" size="small">
                  <el-checkbox-button label="short_answer">简答题</el-checkbox-button>
                  <el-checkbox-button label="single_choice">单选题</el-checkbox-button>
                  <el-checkbox-button label="multiple_choice">多选题</el-checkbox-button>
                  <el-checkbox-button label="programming">编程题</el-checkbox-button>
                </el-checkbox-group>
              </el-form-item>
              <el-form-item label="题目数量"><el-input-number v-model="count" :min="1" :max="30" /></el-form-item>
              <el-form-item label="难度"><el-rate v-model="difficulty" /></el-form-item>
              <el-button type="primary" :loading="submitting" @click="generateAssignment">由出题智能体生成</el-button>
            </el-form>
          </el-card></el-col>
          <el-col :span="5"><el-card class="draft-sidebar" v-loading="draftListLoading">
            <div slot="header" class="result-title"><span>草稿暂存</span><el-tag size="mini">{{ drafts.length }}</el-tag></div>
            <div v-if="pendingDraft" class="draft-item pending-draft" :class="{failed:pendingDraft.status==='failed'||pendingDraft.status==='cancelled'}">
              <div class="draft-item-title"><b>{{ pendingDraft.title }}</b><el-button v-if="pendingDraft.status==='failed'||pendingDraft.status==='cancelled'" type="text" icon="el-icon-close" @click="dismissPendingDraft" /></div>
              <small>{{ pendingDraft.status==='failed' ? '生成失败' : pendingDraft.status==='cancelled' ? '任务已取消' : pendingDraft.status==='queued' ? '等待 Worker 接收任务' : '正在检索资料并生成题目' }}</small>
              <div class="pending-meta"><el-tag size="mini" :type="pendingDraft.status==='failed'?'danger':'primary'"><i v-if="!['failed','cancelled'].includes(pendingDraft.status)" class="el-icon-loading" /> {{ pendingDraft.status==='failed'?'生成失败':pendingDraft.status==='cancelled'?'已取消':'正在生成' }}</el-tag><span>{{ pendingDraft.questionCount }} 题 · 难度 {{ pendingDraft.difficulty }} · {{ pendingDraft.kindText || '简答题' }}</span></div>
            </div>
            <el-empty v-if="!draftListLoading&&!drafts.length&&!pendingDraft" description="尚无 AI 作业草稿" :image-size="70" />
            <div v-for="draft in drafts" :key="draft.id" class="draft-item" :class="{active:selectedDraft&&selectedDraft.id===draft.id}" @click="selectDraft(draft.id)">
              <div class="draft-item-title"><b>{{ draft.title }}</b><el-button type="text" icon="el-icon-delete" @click.stop="deleteDraft(draft)" /></div>
              <small>{{ formatTime(draft.updated_at) }}</small>
              <div><el-tag size="mini" type="warning">草稿</el-tag><span>{{ draft.total_score }} 分</span></div>
            </div>
          </el-card></el-col>
          <el-col :span="12"><el-card class="draft-editor" v-loading="draftLoading">
            <div slot="header" class="result-title">
              <span>草稿编辑区</span>
              <div v-if="selectedDraft">
                <el-button v-if="!draftEditing" size="mini" @click="startDraftEdit">编辑</el-button>
                <el-button v-if="!draftEditing" size="mini" type="success" @click="openPublishDialog">发布作业</el-button>
                <el-button v-if="draftEditing" size="mini" @click="cancelDraftEdit">取消</el-button>
                <el-button v-if="draftEditing" size="mini" type="primary" :loading="draftSaving" @click="saveDraft">保存修改</el-button>
              </div>
            </div>
            <el-empty v-if="!selectedDraft" description="从左侧选择历史草稿，或生成一个新草稿" />
            <template v-if="selectedDraft&&draftForm">
              <el-input v-if="draftEditing" v-model="draftForm.title" maxlength="200" show-word-limit class="draft-title-input" />
              <h3 v-else class="draft-title">{{ selectedDraft.title }}</h3>
              <div class="draft-meta"><el-tag size="small" type="warning">未发布</el-tag><span>{{ selectedDraft.questions.length }} 题</span><span>共 {{ selectedDraft.total_score }} 分</span><span>更新于 {{ formatTime(selectedDraft.updated_at) }}</span></div>
              <el-alert title="草稿仅教师可见，编辑保存后仍不会自动发布" type="warning" :closable="false" />
              <div v-for="(q,index) in draftForm.questions" :key="q.id||`new-${index}`" class="question draft-question">
                <template v-if="draftEditing">
                  <div class="question-toolbar"><b>第 {{ index + 1 }} 题</b><div>
                    <el-select v-model="q.kind" size="mini"><el-option label="简答题" value="short_answer" /><el-option label="单选题" value="single_choice" /><el-option label="多选题" value="multiple_choice" /><el-option label="编程题" value="programming" /></el-select>
                    <el-input-number v-model="q.score" size="mini" :min="1" :max="1000" />
                    <el-rate v-model="q.difficulty" class="inline-rate" />
                    <el-button type="text" class="danger-action" @click="removeDraftQuestion(index)">删除</el-button>
                  </div></div>
                  <el-input v-model="q.prompt" type="textarea" :rows="2" placeholder="题目内容" />
                  <el-input v-model="q.reference_answer" type="textarea" :rows="3" placeholder="参考答案或评分标准" class="answer-input" />
                </template>
                <template v-else>
                  <b>{{ index + 1 }}. {{ q.prompt }}</b><p>参考答案：{{ q.reference_answer || '暂未填写' }}</p>
                  <div class="question-meta"><span>{{ kindLabel(q.kind) }} · 难度 {{ q.difficulty }} · {{ q.score }} 分</span><el-tag v-for="pointId in q.knowledge_point_ids" :key="pointId" size="mini" type="info">{{ knowledgePointName(pointId) }}</el-tag></div>
                </template>
              </div>
              <el-button v-if="draftEditing" icon="el-icon-plus" class="add-question" @click="addDraftQuestion">添加题目</el-button>
              <el-collapse v-if="run.id&&steps.length" class="run-trace">
                <el-collapse-item title="查看本草稿的智能体运行轨迹" name="trace">
                  <div class="run-meta" v-if="run.agent_name">{{ run.agent_name }} · {{ run.task_type }}</div>
                  <el-timeline><el-timeline-item v-for="step in steps" :key="step.position" :timestamp="`${step.duration_ms || 0}ms`"><b>{{ step.node_name }}</b> · {{ step.tool_name || '内部节点' }}<small>{{ step.step_type }}</small></el-timeline-item></el-timeline>
                </el-collapse-item>
              </el-collapse>
            </template>
          </el-card></el-col>
        </el-row>
      </el-tab-pane>

      <el-tab-pane label="课程知识路线" name="courseMap">
        <el-card>
          <div slot="header" class="result-title"><span>教师课程助手生成的路线草稿</span><div>
            <el-button size="small" :loading="mapGenerating" @click="generateCourseMap">从已索引资料生成</el-button>
            <el-button v-if="courseMap && courseMap.status==='draft'" size="small" @click="editing=!editing">{{ editing ? '取消编辑' : '编辑' }}</el-button>
            <el-button v-if="editing" size="small" type="primary" :loading="mapSaving" @click="saveCourseMap">保存修改</el-button>
            <el-button v-if="courseMap && courseMap.status==='draft'" size="small" type="success" @click="publishCourseMap">发布路线</el-button>
          </div></div>
          <el-empty v-if="!courseMap" description="课程资料完成索引后，可生成带资料证据的知识路线" />
          <div v-else class="map-layout">
            <div class="map-list">
              <div class="map-summary"><el-tag :type="courseMap.status==='published'?'success':'warning'">{{ courseMap.status }}</el-tag> v{{ courseMap.version }} · {{ courseMap.summary }}</div>
              <div v-for="(chapter,index) in chapterNodes" :key="chapter.node_key" class="chapter-group">
                <div class="map-node chapter-node" :class="{active:selectedNode&&selectedNode.node_key===chapter.node_key}" @click="selectedNode=chapter">
                  <span>{{ index + 1 }}</span><el-input v-if="editing" v-model="chapter.name" size="mini" /><b v-else>{{ chapter.name }}</b>
                  <div v-if="editing" class="order-actions"><el-button type="text" :disabled="index===0" @click.stop="moveNode(courseMap.nodes.indexOf(chapter),-1)">上移</el-button></div>
                </div>
                <div v-for="point in chapter.children" :key="point.node_key" class="knowledge-point" :class="{active:selectedNode&&selectedNode.node_key===point.node_key}" @click="selectedNode=point">
                  <i></i><el-input v-if="editing" v-model="point.name" size="mini" /><span v-else>{{ point.name }}</span>
                </div>
              </div>
            </div>
            <div><div ref="courseMapChart" class="map-chart"></div>
              <el-card v-if="selectedNode" shadow="never" class="evidence-card">
                <div slot="header"><b>{{ selectedNode.name }}</b><el-tag size="mini">{{ selectedNode.node_type==='chapter'?'章节':'知识点' }}</el-tag></div>
                <p>{{ selectedNode.description || '暂无概要' }}</p>
                <div v-if="selectedNode.node_type==='chapter'&&childrenOf(selectedNode).length" class="point-summary"><b>本章知识点</b><el-tag v-for="point in childrenOf(selectedNode)" :key="point.node_key" size="small" @click="selectedNode=point">{{ point.name }}</el-tag></div>
                <el-collapse v-if="selectedNode.evidence&&selectedNode.evidence.length" class="source-collapse">
                  <el-collapse-item :title="`查看资料依据（${selectedNode.evidence.length}）`">
                    <div v-for="item in selectedNode.evidence" :key="item.chunk_id" class="evidence-item"><el-tag size="mini" type="info">{{ sourceType(item.resource_type) }}</el-tag> 《{{ item.title }}》 {{ locator(item) }}<small>{{ item.excerpt }}</small></div>
                  </el-collapse-item>
                </el-collapse>
              </el-card>
            </div>
          </div>
        </el-card>
      </el-tab-pane>
    </el-tabs>
    <el-dialog title="发布作业" :visible.sync="publishDialogVisible" width="480px" :close-on-click-modal="false" append-to-body>
      <el-alert title="发布后将向本课程学生开放，题目不能再直接覆盖修改" type="warning" :closable="false" show-icon />
      <el-form label-position="top" class="publish-form">
        <el-form-item label="作业开放时间">
          <el-date-picker v-model="publishRange" type="datetimerange" range-separator="至" start-placeholder="开始时间" end-placeholder="截止时间" format="yyyy-MM-dd HH:mm" :picker-options="publishPickerOptions" style="width:100%" />
        </el-form-item>
      </el-form>
      <span slot="footer"><el-button @click="publishDialogVisible=false">取消</el-button><el-button type="primary" :loading="publishSaving" @click="publishDraft">确认发布</el-button></span>
    </el-dialog>
  </div>
</template>

<script>
import apiV1 from '@/utils/apiV1'
import * as echarts from 'echarts'

export default {
  data(){return{activeTab:'assignment',keywords:'',selectedChapterIds:[],questionKinds:['short_answer'],count:5,difficulty:2,submitting:false,pendingDraft:null,run:{},steps:[],timer:null,drafts:[],selectedDraft:null,draftForm:null,draftListLoading:false,draftLoading:false,draftEditing:false,draftSaving:false,publishDialogVisible:false,publishRange:[],publishSaving:false,publishPickerOptions:{disabledDate(time){return time.getTime()<Date.now()-86400000}},courseMap:null,publishedCourseMap:null,mapGenerating:false,mapSaving:false,editing:false,selectedNode:null,chart:null}},
  computed:{
    course(){return this.$store.getters.getCourse||{}},
    offeringId(){return Number(this.course.id||this.course.offeringId||this.course.courseCode)||null},
    chapterNodes(){return this.hierarchicalNodes(this.courseMap)},
    publishedChapters(){return this.hierarchicalNodes(this.publishedCourseMap)}
  },
  created(){this.loadCourseMap();this.loadPublishedCourseMap();this.loadAssignmentDrafts();this.restorePendingDraft()},
  mounted(){window.addEventListener('resize',this.resizeCourseMap)},
  watch:{
    activeTab(value){if(value==='courseMap')this.$nextTick(this.renderCourseMap)},
    offeringId(value,previous){if(value&&value!==previous){this.selectedChapterIds=[];this.run={};this.steps=[];this.pendingDraft=null;this.submitting=false;this.selectedDraft=null;this.draftForm=null;this.loadCourseMap();this.loadPublishedCourseMap();this.loadAssignmentDrafts();this.restorePendingDraft()}}
  },
  beforeDestroy(){if(this.timer)clearTimeout(this.timer);window.removeEventListener('resize',this.resizeCourseMap);if(this.chart)this.chart.dispose()},
  methods:{
    errorMessage(error){return error&&error.response&&error.response.data&&error.response.data.msg||error&&error.message},
    pendingStorageKey(){return `aiedu-assignment-generation-${this.offeringId}`},
    persistPendingDraft(){if(this.pendingDraft&&this.offeringId)localStorage.setItem(this.pendingStorageKey(),JSON.stringify(this.pendingDraft))},
    clearPendingDraft(){if(this.offeringId)localStorage.removeItem(this.pendingStorageKey());this.pendingDraft=null;this.submitting=false},
    restorePendingDraft(){if(!this.offeringId)return;try{const value=JSON.parse(localStorage.getItem(this.pendingStorageKey())||'null');if(!value||!value.runId)return;this.pendingDraft=value;if(['failed','cancelled'].includes(value.status)){this.submitting=false;return}this.submitting=true;this.pollAssignment(value.runId)}catch(_){localStorage.removeItem(this.pendingStorageKey())}},
    dismissPendingDraft(){this.clearPendingDraft()},
    async generateAssignment(){if(!this.offeringId)return this.$message.warning('请先选择课程');if(!this.questionKinds.length)return this.$message.warning('请至少选择一种题型');if(this.questionKinds.length>this.count)return this.$message.warning('题目数量不能少于所选题型数量');const chapters=this.publishedChapters.filter(item=>this.selectedChapterIds.includes(item.id)).map(item=>item.name);const words=this.keywords.split(/[，,\s]+/).filter(Boolean);const selectedKinds=[...this.questionKinds];this.pendingDraft={title:chapters.join('、')||words.join('、')||'新作业草稿',questionCount:this.count,difficulty:this.difficulty,kindText:selectedKinds.map(this.kindLabel).join('、'),status:'queued',runId:null,error:null};this.submitting=true;try{const key=`draft-${this.offeringId}-${Date.now()}`;const res=await apiV1.post(`/teacher/offerings/${this.offeringId}/assignment-drafts`,{keywords:words,course_map_node_ids:this.selectedChapterIds,question_count:this.count,difficulty:this.difficulty,question_kinds:selectedKinds,knowledge_point_ids:[],idempotency_key:key});this.pendingDraft={...this.pendingDraft,runId:res.data.agent_run_id,status:res.data.status};this.persistPendingDraft();this.pollAssignment(res.data.agent_run_id)}catch(error){this.pendingDraft={...this.pendingDraft,status:'failed',error:this.errorMessage(error)||'智能出题任务创建失败'};this.submitting=false;this.persistPendingDraft();this.$message.error(this.pendingDraft.error)}},
    async pollAssignment(runId){if(!this.pendingDraft||this.pendingDraft.runId!==runId)return;try{const current=(await apiV1.get(`/agent-runs/${runId}`)).data;this.pendingDraft={...this.pendingDraft,status:current.status,error:current.error||current.last_error||null};this.persistPendingDraft();if(['succeeded','failed','cancelled'].includes(current.status)){this.submitting=false;if(current.status==='succeeded'&&current.result&&current.result.assignment_id){await this.loadAssignmentDrafts(current.result.assignment_id);this.clearPendingDraft();this.$message.success('新草稿已暂存，可随时返回继续编辑')}else if(current.status==='failed'){this.$message.error(current.error||'智能出题失败')}return}this.timer=setTimeout(()=>this.pollAssignment(runId),1200)}catch(error){this.pendingDraft={...this.pendingDraft,status:'failed',error:this.errorMessage(error)||'读取任务状态失败'};this.submitting=false;this.persistPendingDraft();this.$message.error(this.pendingDraft.error)}},
    async loadAssignmentDrafts(preferredId){if(!this.offeringId)return;this.draftListLoading=true;try{const res=await apiV1.get('/teacher/assignments',{params:{offering_id:this.offeringId,status:'draft',origin:'agent'}});this.drafts=(res.data&&res.data.records)||[];const target=preferredId||this.selectedDraft&&this.selectedDraft.id||this.drafts[0]&&this.drafts[0].id;if(target&&this.drafts.some(item=>item.id===target))await this.openDraft(target);else{this.selectedDraft=null;this.draftForm=null}}catch(error){this.drafts=[];this.$message.error(this.errorMessage(error)||'草稿列表加载失败')}finally{this.draftListLoading=false}},
    async selectDraft(id){if(this.draftEditing&&this.selectedDraft&&this.selectedDraft.id!==id){try{await this.$confirm('当前修改尚未保存，切换草稿将放弃这些修改。','切换草稿',{type:'warning'})}catch(_){return}}await this.openDraft(id)},
    async openDraft(id){this.draftLoading=true;try{const detail=(await apiV1.get(`/teacher/assignments/${id}`)).data;this.selectedDraft=detail;this.draftForm=JSON.parse(JSON.stringify(detail));this.draftEditing=false;if(detail.agent_run_id)await this.loadDraftRun(detail.agent_run_id);else{this.run={};this.steps=[]}}catch(error){this.$message.error(this.errorMessage(error)||'草稿读取失败')}finally{this.draftLoading=false}},
    async loadDraftRun(runId){try{const [runRes,stepsRes]=await Promise.all([apiV1.get(`/agent-runs/${runId}`),apiV1.get(`/agent-runs/${runId}/steps`)]);this.run=runRes.data||{};this.steps=stepsRes.data||[]}catch(_){this.run={};this.steps=[]}},
    startDraftEdit(){this.draftForm=JSON.parse(JSON.stringify(this.selectedDraft));this.draftEditing=true},
    cancelDraftEdit(){this.draftForm=JSON.parse(JSON.stringify(this.selectedDraft));this.draftEditing=false},
    addDraftQuestion(){this.draftForm.questions.push({kind:'short_answer',prompt:'',reference_answer:'',score:10,difficulty:2,knowledge_point_ids:[]})},
    removeDraftQuestion(index){this.draftForm.questions.splice(index,1)},
    async saveDraft(){const title=(this.draftForm.title||'').trim();if(!title)return this.$message.warning('请填写草稿标题');if(this.draftForm.questions.some(item=>!(item.prompt||'').trim()||Number(item.score)<=0))return this.$message.warning('请补全题目内容和有效分值');this.draftSaving=true;try{await apiV1.put(`/teacher/assignments/${this.selectedDraft.id}`,{title,questions:this.draftForm.questions.map(item=>({kind:item.kind,prompt:item.prompt.trim(),reference_answer:(item.reference_answer||'').trim()||null,score:Number(item.score),difficulty:Number(item.difficulty)||0,knowledge_point_ids:item.knowledge_point_ids||[]}))});await this.loadAssignmentDrafts(this.selectedDraft.id);this.$message.success('草稿修改已保存')}catch(error){this.$message.error(this.errorMessage(error)||'草稿保存失败')}finally{this.draftSaving=false}},
    openPublishDialog(){const start=new Date();start.setSeconds(0,0);const end=new Date(start.getTime()+7*24*60*60*1000);this.publishRange=[start,end];this.publishDialogVisible=true},
    localDateTime(value){const date=new Date(value);const pad=number=>String(number).padStart(2,'0');return `${date.getFullYear()}-${pad(date.getMonth()+1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`},
    async publishDraft(){if(!this.selectedDraft)return;if(!this.publishRange||this.publishRange.length!==2)return this.$message.warning('请选择开始时间和截止时间');const [start,end]=this.publishRange.map(value=>new Date(value));if(Number.isNaN(start.getTime())||Number.isNaN(end.getTime())||end<=start)return this.$message.warning('截止时间必须晚于开始时间');this.publishSaving=true;try{await apiV1.post(`/assignments/${this.selectedDraft.id}/publish`,{start_at:this.localDateTime(start),end_at:this.localDateTime(end),idempotency_key:`publish-${this.selectedDraft.id}-${Date.now()}`});this.publishDialogVisible=false;this.selectedDraft=null;this.draftForm=null;this.run={};this.steps=[];await this.loadAssignmentDrafts();this.$message.success('作业已发布，已从草稿暂存栏移入正式作业列表')}catch(error){this.$message.error(this.errorMessage(error)||'发布失败')}finally{this.publishSaving=false}},
    async deleteDraft(draft){try{await this.$confirm(`删除“${draft.title}”后无法恢复，确认删除？`,'删除草稿',{type:'warning'});await apiV1.delete(`/teacher/assignments/${draft.id}`);if(this.selectedDraft&&this.selectedDraft.id===draft.id){this.selectedDraft=null;this.draftForm=null;this.run={};this.steps=[]}await this.loadAssignmentDrafts();this.$message.success('草稿已删除')}catch(error){if(error!=='cancel')this.$message.error(this.errorMessage(error)||'草稿删除失败')}},
    formatTime(value){if(!value)return'--';const date=new Date(value);return Number.isNaN(date.getTime())?value:date.toLocaleString('zh-CN',{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'})},
    kindLabel(value){return{short_answer:'简答题',single_choice:'单选题',multiple_choice:'多选题',programming:'编程题'}[value]||value},
    knowledgePointName(id){const node=(this.publishedCourseMap&&this.publishedCourseMap.nodes||[]).find(item=>Number(item.knowledge_point_id)===Number(id));return node?node.name:`知识点 ${id}`},
    async loadCourseMap(){if(!this.offeringId)return;try{this.courseMap=(await apiV1.get(`/offerings/${this.offeringId}/course-map`)).data;this.selectedNode=this.courseMap&&this.courseMap.nodes[0];if(this.activeTab==='courseMap')this.$nextTick(this.renderCourseMap)}catch(_){this.courseMap=null}},
    async loadPublishedCourseMap(){if(!this.offeringId)return;try{this.publishedCourseMap=(await apiV1.get(`/offerings/${this.offeringId}/course-map?status=published`)).data}catch(_){this.publishedCourseMap=null}},
    async generateCourseMap(){if(!this.offeringId)return this.$message.warning('请先选择课程');this.mapGenerating=true;try{const res=await apiV1.post(`/teacher/offerings/${this.offeringId}/course-map-drafts`,{resource_ids:[],idempotency_key:`course-map-${this.offeringId}-${Date.now()}`});await this.pollMapRun(res.data.agent_run_id)}catch(error){this.$message.error(this.errorMessage(error)||'课程路线生成失败')}finally{this.mapGenerating=false}},
    async pollMapRun(runId){for(let i=0;i<300;i++){const run=(await apiV1.get(`/agent-runs/${runId}`)).data;if(run.status==='succeeded'){await this.loadCourseMap();return}if(run.status==='failed')throw new Error(run.error||'课程路线 Agent 任务失败');await new Promise(resolve=>setTimeout(resolve,1000))}throw new Error('任务超过 5 分钟，请在运行记录中查看状态')},
    moveNode(index,offset){const target=index+offset;if(target<0||target>=this.courseMap.nodes.length)return;const values=this.courseMap.nodes.splice(index,1);this.courseMap.nodes.splice(target,0,values[0]);this.courseMap.nodes.forEach((node,i)=>{node.position=i+1})},
    async saveCourseMap(){this.mapSaving=true;try{const payload={title:this.courseMap.title,summary:this.courseMap.summary,nodes:this.courseMap.nodes.map(node=>({node_key:node.node_key,name:node.name,description:node.description,position:node.position,evidence_chunk_ids:(node.evidence||[]).map(item=>item.chunk_id)})),edges:this.courseMap.edges.map(edge=>({source_key:edge.source_key,target_key:edge.target_key,relation_type:edge.relation_type,evidence_chunk_ids:(edge.evidence||[]).map(item=>item.chunk_id)}))};this.courseMap=(await apiV1.put(`/teacher/course-map-versions/${this.courseMap.id}`,payload)).data;this.editing=false;this.selectedNode=this.courseMap.nodes[0];this.$nextTick(this.renderCourseMap);this.$message.success('路线草稿已保存')}catch(error){this.$message.error(this.errorMessage(error)||'保存失败')}finally{this.mapSaving=false}},
    async publishCourseMap(){try{await this.$confirm('发布后学生可见，并同步章节及其知识点。确认发布？','发布课程路线');this.courseMap=(await apiV1.post(`/teacher/course-map-versions/${this.courseMap.id}/publish`)).data;await this.loadPublishedCourseMap();this.$message.success('课程路线已发布，可在出题智能体中按章节选择');this.$nextTick(this.renderCourseMap)}catch(error){if(error!=='cancel')this.$message.error(this.errorMessage(error)||'发布失败')}},
    hierarchicalNodes(courseMap){if(!courseMap)return[];const edges=(courseMap.edges||[]).filter(edge=>edge.relation_type==='contains');const childrenByKey={};const childKeys=new Set();edges.forEach(edge=>{(childrenByKey[edge.source_key]||(childrenByKey[edge.source_key]=[])).push(edge.target_key);childKeys.add(edge.target_key)});const byKey=Object.fromEntries(courseMap.nodes.map(node=>[node.node_key,node]));const roots=courseMap.nodes.filter(node=>!childKeys.has(node.node_key));return roots.map(node=>({...node,children:(childrenByKey[node.node_key]||[]).map(key=>byKey[key]).filter(Boolean)}))},
    childrenOf(node){const chapter=this.chapterNodes.find(item=>item.node_key===node.node_key);return chapter?chapter.children:[]},
    sourceType(value){return{syllabus:'大纲',textbook:'教材',courseware:'课件'}[value]||'资料'},
    locator(item){if(item.page_number)return `第 ${item.page_number} 页`;if(item.slide_number)return `第 ${item.slide_number} 张幻灯片`;return item.heading_path||`片段 ${item.position+1}`},
    resizeCourseMap(){if(this.chart&&this.activeTab==='courseMap')this.chart.resize()},
    renderCourseMap(){const container=this.$refs.courseMapChart;if(!this.courseMap||!container||container.clientWidth===0)return;if(!this.chart||this.chart.isDisposed())this.chart=echarts.init(container);this.chart.setOption({tooltip:{},series:[{type:'graph',layout:'force',roam:true,label:{show:true},force:{repulsion:220,edgeLength:100},data:this.courseMap.nodes.map(node=>({id:node.node_key,name:node.name,value:node.confidence,symbolSize:44})),links:this.courseMap.edges.map(edge=>({source:edge.source_key,target:edge.target_key,label:{show:true,formatter:edge.relation_type}}))}]},true);this.chart.resize();this.chart.off('click');this.chart.on('click',params=>{const node=this.courseMap.nodes.find(item=>item.node_key===params.data.id);if(node)this.selectedNode=node})}
  }
}
</script>

<style scoped>
.page-shell{padding:32px 48px;min-height:80vh;background:#f6f8fb}.page-heading{margin-bottom:20px}h2{margin:0 0 8px}p{color:#7b8794}.result-title{display:flex;justify-content:space-between;align-items:center}.assignment-workspace{height:calc(100vh - 230px);min-height:620px;max-height:820px}.assignment-workspace>.el-col{height:100%}.assignment-workspace>.el-col>.el-card{height:100%;display:flex;flex-direction:column}.assignment-workspace ::v-deep .el-card__header{flex:0 0 auto}.assignment-workspace ::v-deep .el-card__body{flex:1;min-height:0;overflow-y:auto;box-sizing:border-box}.draft-item{padding:12px;margin-bottom:9px;border:1px solid #e4e7ed;border-radius:8px;cursor:pointer;background:#fbfcfe;transition:.2s}.draft-item:hover,.draft-item.active{border-color:#409eff;background:#ecf5ff}.pending-draft{cursor:default;border-color:#8cc5ff;background:linear-gradient(110deg,#ecf5ff 30%,#f8fbff 45%,#ecf5ff 60%);background-size:240% 100%;animation:draft-loading 1.8s linear infinite}.pending-draft.failed{border-color:#fbc4c4;background:#fef0f0;animation:none}.pending-meta{display:flex;align-items:center}.draft-item-title{display:flex;align-items:flex-start;justify-content:space-between;gap:6px}.draft-item-title b{font-size:13px;line-height:1.5}.draft-item small{display:block;margin:5px 0 8px;color:#909399}.draft-item span{margin-left:7px;color:#697582;font-size:12px}.draft-title{margin:14px 0}.draft-title-input{margin:14px 0 10px}.draft-meta{display:flex;align-items:center;flex-wrap:wrap;gap:10px;margin-bottom:14px;color:#7b8794;font-size:13px}.publish-form{margin-top:18px}.question{padding:16px 0;border-bottom:1px solid #edf0f3}.question p{line-height:1.7}.question span,.run-meta{color:#7b8794;font-size:13px}.question-toolbar{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:10px}.question-toolbar>div{display:flex;align-items:center;gap:8px}.question-toolbar .el-select{width:100px}.inline-rate{display:inline-flex}.danger-action{color:#f56c6c}.answer-input{margin-top:9px}.question-meta{display:flex;align-items:center;flex-wrap:wrap;gap:7px}.add-question{width:100%;margin-top:14px}.run-trace{margin-top:18px}.run-meta{margin:10px 0}.el-timeline{margin-top:18px}.el-timeline small{display:block;color:#9aa5b1}.chapter-selector{display:flex;flex-direction:column;gap:9px}.assignment-chapter{padding:10px 12px;border:1px solid #e4e7ed;border-radius:8px;background:#fbfcfe}.chapter-selector small{margin-left:8px;color:#909399;font-weight:400}.assignment-points{display:flex;flex-wrap:wrap;gap:5px 12px;margin:8px 0 0 24px;color:#697582;font-size:12px;line-height:1.5}.assignment-points span::before{content:'·';margin-right:5px;color:#409eff;font-weight:700}.assignment-points.empty{color:#a7afb8}.map-layout{display:grid;grid-template-columns:360px minmax(480px,1fr);gap:20px;align-items:start}.map-list{max-height:calc(100vh - 285px);min-height:420px;overflow-y:auto;padding-right:8px;scrollbar-gutter:stable}.map-summary{margin-bottom:14px;color:#66717d;line-height:1.7}.chapter-group{margin-bottom:10px}.map-node{display:flex;align-items:center;gap:10px;padding:12px;border:1px solid #dfe5ec;border-radius:8px;margin-bottom:5px;cursor:pointer;background:#fff}.map-node.active,.knowledge-point.active{border-color:#409eff;background:#ecf5ff}.map-node>span{display:flex;width:24px;height:24px;border-radius:50%;background:#409eff;color:#fff;align-items:center;justify-content:center}.map-node b{flex:1}.knowledge-point{display:flex;align-items:center;gap:9px;margin:3px 0 3px 22px;padding:7px 10px;border:1px solid transparent;border-radius:6px;color:#56616d;cursor:pointer}.knowledge-point i{width:7px;height:7px;border-radius:50%;background:#8abcf0}.order-actions{margin-left:auto;white-space:nowrap}.map-chart{height:420px;background:#fbfcfe;border-radius:8px}.evidence-card{margin-top:14px}.evidence-card [slot=header]{display:flex;align-items:center;gap:8px}.point-summary{display:flex;align-items:center;flex-wrap:wrap;gap:8px;margin:14px 0}.point-summary .el-tag{cursor:pointer}.source-collapse{margin-top:16px}.evidence-item{padding:10px 0;border-top:1px solid #edf0f3}.evidence-item small{display:block;color:#7b8794;margin-top:5px;line-height:1.5}.el-input{flex:1}@keyframes draft-loading{0%{background-position:100% 0}100%{background-position:-100% 0}}@media(max-width:1200px){.assignment-workspace{height:auto;max-height:none}.assignment-workspace>.el-col{width:100%;height:640px;margin-bottom:16px}.map-layout{grid-template-columns:1fr}.map-list{max-height:560px;min-height:0}}
</style>
