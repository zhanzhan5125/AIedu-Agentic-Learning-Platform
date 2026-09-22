<template>
  <div class="page-shell">
    <div class="page-heading"><h2>课程多智能体工作台</h2><p>四个业务智能体按边界协作；所有计划、工具调用、委派和校验均可追溯。</p></div>
    <el-tabs v-model="activeTab">
      <el-tab-pane label="出题智能体" name="assignment">
        <el-row :gutter="20">
          <el-col :span="9"><el-card><div slot="header">生成作业草稿</div>
            <el-form label-position="top">
              <el-form-item label="关键词"><el-input v-model="keywords" placeholder="例如：递归、二叉树、复杂度" /></el-form-item>
              <el-form-item label="按已发布课程路线选择章节">
                <el-checkbox-group v-if="publishedChapters.length" v-model="selectedChapterIds" class="chapter-selector">
                  <el-checkbox v-for="chapter in publishedChapters" :key="chapter.id" :label="chapter.id">
                    {{ chapter.name }}<small>{{ chapter.children.length }} 个知识点</small>
                  </el-checkbox>
                </el-checkbox-group>
                <el-alert v-else title="发布课程路线后，可按章节约束出题范围" type="info" :closable="false" show-icon />
              </el-form-item>
              <el-form-item label="题目数量"><el-input-number v-model="count" :min="1" :max="30" /></el-form-item>
              <el-form-item label="难度"><el-rate v-model="difficulty" /></el-form-item>
              <el-button type="primary" :loading="submitting" @click="generateAssignment">由出题智能体生成</el-button>
            </el-form>
          </el-card></el-col>
          <el-col :span="15"><el-card><div slot="header" class="result-title"><span>智能体运行结果</span><el-tag v-if="run.status">{{ run.status }}</el-tag></div>
            <el-empty v-if="!run.id" description="提交任务后可查看结构化结果和执行轨迹" />
            <template v-else>
              <el-alert v-if="run.result" title="以下内容是草稿，发布前必须由教师审核" type="warning" :closable="false" />
              <div class="run-meta" v-if="run.agent_name">{{ run.agent_name }} · {{ run.task_type }} · Reflection {{ run.reflection_count || 0 }} 次</div>
              <div v-for="(q,index) in questions" :key="index" class="question"><b>{{ index + 1 }}. {{ q.prompt }}</b><p>参考标准：{{ q.reference_answer }}</p><span>难度 {{ q.difficulty }} · {{ q.score }} 分 · 引用 {{ (q.citations || []).length }} 条</span></div>
              <el-timeline><el-timeline-item v-for="step in steps" :key="step.position" :timestamp="`${step.duration_ms || 0}ms`"><b>{{ step.node_name }}</b> · {{ step.tool_name || '内部节点' }}<small>{{ step.step_type }}</small></el-timeline-item></el-timeline>
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
  </div>
</template>

<script>
import apiV1 from '@/utils/apiV1'
import * as echarts from 'echarts'

export default {
  data(){return{activeTab:'assignment',keywords:'',selectedChapterIds:[],count:5,difficulty:2,submitting:false,run:{},steps:[],timer:null,courseMap:null,publishedCourseMap:null,mapGenerating:false,mapSaving:false,editing:false,selectedNode:null,chart:null}},
  computed:{
    course(){return this.$store.getters.getCourse||{}},
    offeringId(){return Number(this.course.id||this.course.offeringId||this.course.courseCode)||null},
    questions(){return (this.run.result&&this.run.result.questions)||[]},
    chapterNodes(){return this.hierarchicalNodes(this.courseMap)},
    publishedChapters(){return this.hierarchicalNodes(this.publishedCourseMap)}
  },
  created(){this.loadCourseMap();this.loadPublishedCourseMap()},
  mounted(){window.addEventListener('resize',this.resizeCourseMap)},
  watch:{
    activeTab(value){if(value==='courseMap')this.$nextTick(this.renderCourseMap)},
    offeringId(value,previous){if(value&&value!==previous){this.selectedChapterIds=[];this.loadCourseMap();this.loadPublishedCourseMap()}}
  },
  beforeDestroy(){if(this.timer)clearTimeout(this.timer);window.removeEventListener('resize',this.resizeCourseMap);if(this.chart)this.chart.dispose()},
  methods:{
    errorMessage(error){return error&&error.response&&error.response.data&&error.response.data.msg||error&&error.message},
    async generateAssignment(){if(!this.offeringId)return this.$message.warning('请先选择课程');this.submitting=true;try{const key=`draft-${this.offeringId}-${Date.now()}`;const res=await apiV1.post(`/teacher/offerings/${this.offeringId}/assignment-drafts`,{keywords:this.keywords.split(/[，,\s]+/).filter(Boolean),course_map_node_ids:this.selectedChapterIds,question_count:this.count,difficulty:this.difficulty,question_kinds:['short_answer'],knowledge_point_ids:[],idempotency_key:key});this.run={id:res.data.agent_run_id,status:res.data.status};this.pollAssignment()}catch(error){this.$message.error(this.errorMessage(error)||'智能出题任务创建失败');this.submitting=false}},
    async pollAssignment(){const res=await apiV1.get(`/agent-runs/${this.run.id}`);this.run=res.data;if(['succeeded','failed','cancelled'].includes(this.run.status)){this.submitting=false;this.steps=(await apiV1.get(`/agent-runs/${this.run.id}/steps`)).data||[];return}this.timer=setTimeout(()=>this.pollAssignment(),1200)},
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
.page-shell{padding:32px 48px;min-height:80vh;background:#f6f8fb}.page-heading{margin-bottom:20px}h2{margin:0 0 8px}p{color:#7b8794}.result-title{display:flex;justify-content:space-between;align-items:center}.question{padding:16px 0;border-bottom:1px solid #edf0f3}.question span,.run-meta{color:#7b8794;font-size:13px}.run-meta{margin:14px 0}.el-timeline{margin-top:24px}.el-timeline small{display:block;color:#9aa5b1}.chapter-selector{display:flex;flex-direction:column;gap:7px}.chapter-selector small{margin-left:8px;color:#909399}.map-layout{display:grid;grid-template-columns:360px minmax(480px,1fr);gap:20px}.map-summary{margin-bottom:14px;color:#66717d;line-height:1.7}.chapter-group{margin-bottom:10px}.map-node{display:flex;align-items:center;gap:10px;padding:12px;border:1px solid #dfe5ec;border-radius:8px;margin-bottom:5px;cursor:pointer;background:#fff}.map-node.active,.knowledge-point.active{border-color:#409eff;background:#ecf5ff}.map-node>span{display:flex;width:24px;height:24px;border-radius:50%;background:#409eff;color:#fff;align-items:center;justify-content:center}.map-node b{flex:1}.knowledge-point{display:flex;align-items:center;gap:9px;margin:3px 0 3px 22px;padding:7px 10px;border:1px solid transparent;border-radius:6px;color:#56616d;cursor:pointer}.knowledge-point i{width:7px;height:7px;border-radius:50%;background:#8abcf0}.order-actions{margin-left:auto;white-space:nowrap}.map-chart{height:420px;background:#fbfcfe;border-radius:8px}.evidence-card{margin-top:14px}.evidence-card [slot=header]{display:flex;align-items:center;gap:8px}.point-summary{display:flex;align-items:center;flex-wrap:wrap;gap:8px;margin:14px 0}.point-summary .el-tag{cursor:pointer}.source-collapse{margin-top:16px}.evidence-item{padding:10px 0;border-top:1px solid #edf0f3}.evidence-item small{display:block;color:#7b8794;margin-top:5px;line-height:1.5}.el-input{flex:1}
</style>
