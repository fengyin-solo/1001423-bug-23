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
          <td v-for="column in columns" :key="column">{{ row[column] ?? '—' }}</td>
          <td class="row-actions">
            <button class="link" type="button" @click="openDetail(row)">详情</button>
            <template v-for="action in actions" :key="action">
              <button
                v-if="actionAvailable(action, row)"
                class="link"
                type="button"
                @click="runAction(action, row)"
              >
                {{ action }}
              </button>
            </template>
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

    <div v-if="detail" class="modal-mask" @click.self="closeDetail">
      <div class="modal-card">
        <header class="modal-head">
          <h3>病害记录详情</h3>
          <button class="btn ghost" type="button" @click="closeDetail">关闭</button>
        </header>
        <dl class="detail-grid">
          <template v-for="field in detailFields" :key="field">
            <dt>{{ field }}</dt>
            <dd>{{ detail[field] ?? '—' }}</dd>
          </template>
        </dl>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>
type StatItem = { label: string; value: number }

const ENDPOINT = '/api/disease'
const columns = ["病害编号", "所在设施", "病害类型", "病害位置", "严重等级", "发现日期", "登记人员", "病害状态"]
const actions = ["确认定级", "提交闭环", "挂起病害"]
const statuses = ["待定级", "已定级", "处置中", "已闭环", "已挂起"]
const detailFields = [...columns, "挂起理由"]

const rows = ref<Row[]>([])
const total = ref(0)
const stats = ref<StatItem[]>([
  { label: '待定级病害', value: 0 },
  { label: '处置中病害', value: 0 },
  { label: '超期未闭环', value: 0 },
])
const detail = ref<Row | null>(null)
const errorMessage = ref('')
const noticeMessage = ref('')
const filters = ref<Record<string, string>>({})
const filterFields = columns.slice(0, 3)

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

function actionAvailable(action: string, row: Row) {
  // 已闭环的病害不能再挂起，前端直接不给出入口，后端同样会拦
  return !(action === '挂起病害' && row['病害状态'] === '已闭环')
}

async function openDetail(row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}`)
    if (!response.ok) {
      throw new Error('病害记录详情读取失败')
    }
    detail.value = (await response.json()) as Row
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '病害记录详情读取失败'
  }
}

function closeDetail() {
  detail.value = null
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  noticeMessage.value = ''
  const values: Record<string, string> = { action }
  if (action === '挂起病害') {
    const reason = window.prompt('请输入挂起理由（必填）')
    if (reason === null) return
    if (!reason.trim()) {
      errorMessage.value = '挂起理由未填写，无法挂起'
      return
    }
    values['挂起理由'] = reason.trim()
  } else if (action === '确认定级') {
    const grade = window.prompt('请输入定级结论（严重等级），留空则沿用上一次生效值')
    if (grade === null) return
    if (grade.trim()) values['严重等级'] = grade.trim()
  } else if (action === '提交闭环') {
    if (!window.confirm('确认提交闭环？闭环后该病害不能再挂起')) return
  }
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values }),
    })
    const payload = await response.json()
    if (!response.ok || !payload.ok) {
      throw new Error(payload?.message ?? payload?.detail ?? '病害登记动作未生效，请稍后重试')
    }
    noticeMessage.value = payload.message ?? '操作已完成'
    if (payload.entry) {
      const index = rows.value.findIndex((item) => String(item.id) === String(row.id))
      if (index >= 0) rows.value[index] = { ...rows.value[index], ...payload.entry }
    }
    await Promise.all([reload(), loadStats()])
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '病害登记操作失败'
  }
}

async function reload() {
  const query = new URLSearchParams(filters.value as Record<string, string>).toString()
  try {
    const response = await request(`${ENDPOINT}?${query}`)
    if (!response.ok) {
      throw new Error('病害记录列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '病害登记列表读取失败'
  }
}

async function loadStats() {
  try {
    const response = await request(`${ENDPOINT}/stats`)
    if (!response.ok) {
      throw new Error('病害统计读取失败')
    }
    const payload = await response.json()
    stats.value = payload.items ?? stats.value
  } catch {
    // 统计卡读取失败时保留上一次结果，不打扰列表操作
  }
}

onMounted(() => {
  void reload()
  void loadStats()
})
</script>
