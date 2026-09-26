<template>
  <section class="page" data-module="disease">
    <header class="page-head">
      <div>
        <h2>病害登记管理</h2>
        <p class="page-desc">维护病害记录，围绕病害编号、所在设施、病害类型、病害位置做登记、筛选与状态流转。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记病害记录</button>
        <button class="btn" type="button" @click="exportRows">导出病害登记清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label v-for="field in filterFields" :key="field" class="filter-item">
        <span>{{ field }}</span>
        <input v-model="filters[field]" :placeholder="`按${field}检索`" />
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">{{ row[column] || '—' }}</td>
          <td class="row-actions">
            <button class="link" type="button" @click="openDetail(row)">详情</button>
            <button
              v-for="action in actions"
              :key="action"
              class="link"
              type="button"
              :disabled="action === '挂起病害' && row.status === '已闭环'"
              :title="action === '挂起病害' && row.status === '已闭环' ? '已闭环的病害不能再挂起' : ''"
              @click="startAction(action, row)"
            >
              {{ action }}
            </button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无病害登记数据，可先登记病害记录</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条病害登记记录</span>
      <span v-if="noticeMessage" class="notice-text">{{ noticeMessage }}</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>

    <div v-if="detail" class="overlay" @click.self="closeDetail">
      <aside class="panel">
        <header class="panel-head">
          <h3>病害详情 · {{ detail.病害编号 }}</h3>
          <button class="link" type="button" @click="closeDetail">关闭</button>
        </header>
        <dl class="detail-grid">
          <template v-for="field in detailFields" :key="field">
            <dt>{{ field }}</dt>
            <dd>{{ detail[field] || '—' }}</dd>
          </template>
          <template v-if="detail.挂起理由">
            <dt>挂起理由</dt>
            <dd>{{ detail.挂起理由 }}</dd>
          </template>
        </dl>
      </aside>
    </div>

    <div v-if="pendingAction" class="overlay" @click.self="cancelAction">
      <form class="panel" @submit.prevent="confirmAction">
        <header class="panel-head">
          <h3>{{ pendingAction.action }} · {{ pendingAction.row.病害编号 }}</h3>
          <button class="link" type="button" @click="cancelAction">取消</button>
        </header>
        <label v-if="pendingAction.action === '挂起病害'" class="dialog-field">
          <span>挂起理由（必填，未填写会被拦截）</span>
          <textarea v-model="actionForm.挂起理由" rows="3" placeholder="请填写挂起理由"></textarea>
        </label>
        <label v-else-if="pendingAction.action === '确认定级'" class="dialog-field">
          <span>定级结论（严重等级）</span>
          <input v-model="actionForm.严重等级" placeholder="留空则沿用上一次生效的严重等级" />
        </label>
        <p v-if="actionError" class="error-text">{{ actionError }}</p>
        <footer class="panel-foot">
          <button class="btn primary" type="submit">确认{{ pendingAction.action }}</button>
        </footer>
      </form>
    </div>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>

const ENDPOINT = '/api/disease'
const columns = ["病害编号", "所在设施", "病害类型", "病害位置", "严重等级", "发现日期", "登记人员", "病害状态"]
const actions = ["确认定级", "提交闭环", "挂起病害"]
const detailFields = columns

const rows = ref<Row[]>([])
const stats = ref<{ label: string; value: number }[]>([])
const total = ref(0)
const errorMessage = ref('')
const noticeMessage = ref('')
const filters = ref<Record<string, string>>({})
const filterFields = columns.slice(0, 3)
const detail = ref<Row | null>(null)
const pendingAction = ref<{ action: string; row: Row } | null>(null)
const actionForm = ref<Record<string, string>>({})
const actionError = ref('')

function resetFilters() {
  filters.value = {}
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  errorMessage.value = '病害记录登记入口尚未接入审批流'
}

function startAction(action: string, row: Row) {
  errorMessage.value = ''
  noticeMessage.value = ''
  if (action === '提交闭环') {
    void submitAction(action, row, {})
    return
  }
  actionForm.value = {}
  actionError.value = ''
  pendingAction.value = { action, row }
}

function cancelAction() {
  pendingAction.value = null
  actionError.value = ''
}

async function confirmAction() {
  const pending = pendingAction.value
  if (!pending) return
  const values: Record<string, string> = {}
  if (pending.action === '挂起病害') {
    const reason = (actionForm.value.挂起理由 ?? '').trim()
    if (!reason) {
      actionError.value = '挂起理由未填写，请先补充挂起理由再执行挂起'
      return
    }
    values.挂起理由 = reason
  }
  if (pending.action === '确认定级') {
    values.严重等级 = (actionForm.value.严重等级 ?? '').trim()
  }
  const ok = await submitAction(pending.action, pending.row, values)
  if (ok) {
    pendingAction.value = null
  } else {
    actionError.value = errorMessage.value
  }
}

async function submitAction(action: string, row: Row, values: Record<string, string>): Promise<boolean> {
  errorMessage.value = ''
  noticeMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action, ...values } }),
    })
    const payload = await response.json()
    if (!response.ok || !payload.ok) {
      throw new Error(payload?.message ?? payload?.detail ?? '病害登记动作未生效，请稍后重试')
    }
    noticeMessage.value = payload.message ?? `病害记录已${action}`
    if (payload.entry) {
      rows.value = rows.value.map((item) => (item.id === row.id ? { ...item, ...payload.entry } : item))
      if (detail.value && detail.value.id === row.id) {
        detail.value = { ...detail.value, ...payload.entry }
      }
    }
    await Promise.all([reload(), loadStats()])
    return true
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '病害登记操作失败'
    return false
  }
}

async function openDetail(row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}`)
    if (!response.ok) {
      throw new Error('病害详情读取失败')
    }
    detail.value = await response.json()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '病害详情读取失败'
  }
}

function closeDetail() {
  detail.value = null
}

async function loadStats() {
  const response = await request(`${ENDPOINT}/stats`)
  if (!response.ok) {
    throw new Error('病害统计数据读取失败')
  }
  const payload = await response.json()
  stats.value = payload.items ?? []
}

async function reload() {
  const query = new URLSearchParams(filters.value as Record<string, string>).toString()
  const response = await request(`${ENDPOINT}?${query}`)
  if (!response.ok) {
    throw new Error('病害记录列表读取失败')
  }
  const payload = await response.json()
  rows.value = payload.items ?? []
  total.value = payload.total ?? rows.value.length
}

async function loadPage() {
  errorMessage.value = ''
  try {
    await Promise.all([reload(), loadStats()])
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '病害登记数据读取失败'
  }
}

onMounted(loadPage)
</script>

<style scoped>
.overlay {
  position: fixed;
  inset: 0;
  background: rgba(15, 23, 42, 0.35);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 10;
}
.panel {
  background: #fff;
  border-radius: 8px;
  padding: 16px;
  width: 420px;
  max-width: 90vw;
}
.panel-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}
.panel-head h3 {
  margin: 0;
  font-size: 15px;
}
.panel-foot {
  display: flex;
  justify-content: flex-end;
  margin-top: 12px;
}
.detail-grid {
  display: grid;
  grid-template-columns: 96px 1fr;
  gap: 6px 12px;
  margin: 0;
  font-size: 13px;
}
.detail-grid dt {
  color: var(--muted);
}
.detail-grid dd {
  margin: 0;
}
.dialog-field span {
  display: block;
  font-size: 12px;
  color: var(--muted);
  margin-bottom: 4px;
}
.dialog-field input,
.dialog-field textarea {
  width: 100%;
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 6px 8px;
  font-size: 13px;
  font-family: inherit;
}
.link:disabled {
  color: var(--muted);
  cursor: not-allowed;
}
.notice-text {
  color: #067647;
}
</style>
