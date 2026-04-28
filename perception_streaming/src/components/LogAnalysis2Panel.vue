<template>
  <div class="la2-root">
    <!-- Input Bar -->
    <div class="la2-input-bar">
      <label>📷 Camera 包路徑:</label>
      <input v-model="camBagPath" class="la2-path-input" placeholder="camera bag 文件夾路徑" />
      <button class="la2-extract-btn" :disabled="extracting" @click="doExtractCamera">
        {{ extracting && extractType === 'camera' ? '⏳ 提取中...' : '📦 提取圖片 + 點雲' }}
      </button>
      <label>🚗 Nav 包路徑:</label>
      <input v-model="navBagPath" class="la2-path-input" placeholder="nav bag 文件夾路徑" />
      <button class="la2-extract-btn" :disabled="extracting" @click="doExtractNav">
        {{ extracting && extractType === 'nav' ? '⏳ 提取中...' : '📦 提取圖片 + 點雲' }}
      </button>
      <button class="la2-extract-btn" :disabled="loadingPreview" @click="loadDefaultPreview" style="background:#1a5490;border-color:#2563eb">
        {{ loadingPreview ? '⏳ 加載中...' : '🔄 加載預覽' }}
      </button>
    </div>

    <!-- Preview Section -->
    <div v-if="previewImages.length" class="la2-preview-section">
      <div class="la2-preview-header">
        <span>📷 圖片預覽 ({{ previewImages.length }} 張)</span>
        <span v-if="previewSelectedIdx >= 0" class="la2-preview-info">{{ previewSelectedIdx + 1 }} / {{ previewImages.length }}</span>
      </div>
      <div class="la2-preview-body">
        <div class="la2-preview-thumbs">
          <div
            v-for="(img, idx) in previewImages.slice(0, 50)"
            :key="img"
            class="la2-preview-thumb"
            :class="{ active: previewSelectedIdx === idx }"
            @click="previewSelectedIdx = idx"
          >
            <img :src="getPreviewImageUrl(img)" loading="lazy" />
            <div class="la2-preview-thumb-label">{{ idx + 1 }}</div>
          </div>
        </div>
        <div v-if="previewSelectedIdx >= 0" class="la2-preview-main">
          <img :src="getPreviewImageUrl(previewImages[previewSelectedIdx])" @click="openLb(getPreviewImageUrl(previewImages[previewSelectedIdx]), previewImages[previewSelectedIdx])" />
        </div>
      </div>
    </div>

    <div v-if="extractLogVisible" class="la2-extract-log" ref="extractLogEl">
      <div v-for="(line, i) in extractLogs" :key="i" :class="{ 'log-err': line.startsWith('ERROR') || line.startsWith('❌') }">{{ line }}</div>
    </div>

    <!-- Header Info Cards -->
    <div class="la2-header">
      <h1>⚠ 誤避障分析可視化報告 — LK-MR6P1US000111</h1>
      <div class="la2-info-grid">
        <div class="la2-info-card">
          <h3>📦 NAV 包</h3>
          <div class="la2-val">
            <b>rosbag_LK-MR6P1US000111_navigation_202603270322</b><br>
            時間範圍: <b>03:22:22 ~ 03:23:32</b><br>
            話題: /cmd_vel(806) /decision_assistant/move_abnormal(47)<br>
            圖像: /camera_sensors/...(415) 點雲: /perception_node/stereo/pcl_output(340)
          </div>
        </div>
        <div class="la2-info-card">
          <h3>📷 CAMERA 包</h3>
          <div class="la2-val">
            <b>rosbag_LK-MR6P1US000111_camera_202603220059</b><br>
            時間範圍: <b>00:59:12 ~ 00:59:42 (2026-03-22)</b><br>
            左目(154) 右目(158) 點雲(115)<br>
            里程計: /chassis/odom_raw(1207) 全程靜止
          </div>
        </div>
        <div class="la2-info-card">
          <h3>📋 停障統計 (NAV)</h3>
          <div class="la2-val">
            停障次數: <b>4次</b><br>
            最長停障: <b>4.62s</b> (stop1 03:22:50)<br>
            最近障礙距離: <b>0.10m</b><br>
            label=3(stat) 最多: <b>478點</b>
          </div>
        </div>
        <div class="la2-info-card">
          <h3>📋 誤避障統計 (CAMERA)</h3>
          <div class="la2-val">
            分析幀數: <b>115幀</b> (全部異常)<br>
            Top1 close_stat: <b>491點</b><br>
            最近 stat 距離: <b>0.05m</b><br>
            提取樣本: <b>Top5 × 4~5幀</b>
          </div>
        </div>
      </div>
    </div>

    <!-- Main Tabs -->
    <div class="la2-tabs">
      <button class="la2-tab-btn" :class="{ active: mainTab === 'nav' }" @click="mainTab = 'nav'">🚗 NAV 包分析</button>
      <button class="la2-tab-btn" :class="{ active: mainTab === 'camera' }" @click="mainTab = 'camera'">📷 CAMERA 包分析</button>
      <button class="la2-tab-btn" :class="{ active: mainTab === 'conclusion' }" @click="mainTab = 'conclusion'">📊 分析結論</button>
    </div>

    <!-- NAV Panel -->
    <div v-if="mainTab === 'nav'" class="la2-panel">
      <div class="la2-sub-tabs">
        <button v-for="s in navStops" :key="s.id" class="la2-sub-btn" :class="{ active: navSub === s.id }" @click="navSub = s.id; loadNavStopFrames(s.id)">{{ s.label }}</button>
        <button class="la2-sub-btn" :class="{ active: navSub === 'pcd' }" @click="navSub = 'pcd'">🔵 點雲可視化</button>
      </div>

      <template v-for="s in navStops" :key="s.id">
      <div v-if="navSub === s.id">
        <div class="la2-abox">
          <h3>{{ s.title }}</h3>
          <span v-html="s.desc"></span>
          <div class="la2-verdict" :class="s.verdictClass">{{ s.verdict }}</div>
        </div>
        <div v-if="extractedFrames.length" class="la2-inline-panel">
          <div class="la2-extracted-header">
            <span>📷 圖像預覽（三列布局）— 共 {{ extractedFrames.length }} 幀</span>
            <span v-if="extractedIdx >= 0" class="la2-ext-nav-info">{{ extractedIdx + 1 }} / {{ extractedFrames.length }} — {{ extractedFrames[extractedIdx].label }}</span>
            <div style="display:flex;gap:6px;align-items:center">
              <button class="la2-nav-btn" :disabled="extractedIdx <= 0" @click="selectExtracted(extractedIdx - 1)">◀</button>
              <button class="la2-nav-btn" :disabled="extractedIdx >= extractedFrames.length - 1" @click="selectExtracted(extractedIdx + 1)">▶</button>
            </div>
          </div>
          <div class="la2-extracted-body-3col">
            <div class="la2-thumb-column">
              <div v-for="(fr, i) in extractedFrames" :key="fr.img" class="la2-ext-thumb-vertical" :class="{ active: extractedIdx === i }" @click="selectExtracted(i)">
                <img :src="extractedImgUrl(fr.img)" loading="lazy" />
                <div class="la2-lbl">{{ i + 1 }}</div>
              </div>
            </div>
            <div class="la2-extracted-img-main">
              <div v-if="extractedIdx < 0" class="la2-pcd-empty">點擊左側縮圖選擇幀</div>
              <img v-else :src="extractedImgUrl(extractedFrames[extractedIdx].img)" class="la2-ext-img-full" />
            </div>
            <div class="la2-extracted-pcd">
              <div v-if="extractedIdx < 0" class="la2-pcd-empty">選擇幀後顯示對應點雲</div>
              <div v-else class="la2-ext-pcd-canvas la2-extract-pcd-slot"></div>
            </div>
          </div>
        </div>
      </div>
      </template>

      <div v-show="navSub === 'pcd'">
        <div class="la2-abox">
          <h3>🔵 NAV 包點雲可視化（label著色）</h3>
          著色規則：<span style="color:#66c466">■ label=2 grass(草地)</span>　<span style="color:#ff0000">■ label=5 static_obstacle(靜態障礙物)</span>　<span style="color:#ff6600">■ label=6 wall</span>　<span style="color:#888">■ 其他</span>
        </div>
        <div class="la2-legend">
          <span class="la2-li"><span class="la2-dot grass"></span>label=2 grass</span>
          <span class="la2-li"><span class="la2-dot road"></span>label=3 road</span>
          <span class="la2-li"><span class="la2-dot stat5"></span>label=5 static_obstacle</span>
          <span class="la2-li"><span class="la2-dot unk"></span>其他</span>
        </div>
        <div class="la2-pcd-wrap">
          <div class="la2-pcd-list">
            <div v-for="(f, i) in navPcdFiles" :key="f" class="la2-pcd-item" :class="{ sel: navSelPcd === f }" @click="loadNavPcd(f)">
              <div class="la2-pn">NAV #{{ i+1 }}</div>
              <div class="la2-ps">{{ f }}</div>
            </div>
            <div v-if="!navPcdFiles.length" class="la2-pcd-empty">暫無 NAV .bin 點雲文件</div>
          </div>
          <canvas ref="navPcdCanvas" class="la2-pcd-canvas"></canvas>
        </div>
      </div>
    </div>

    <!-- CAMERA Panel -->
    <div v-if="mainTab === 'camera'" class="la2-panel">
      <div class="la2-sub-tabs">
        <button v-for="t in camTops" :key="t.id" class="la2-sub-btn" :class="{ active: camSub === t.id }" @click="camSub = t.id; loadCamTopFrames(t.id)">{{ t.label }}</button>
        <button class="la2-sub-btn" :class="{ active: camSub === 'pcd' }" @click="camSub = 'pcd'">🔵 點雲可視化</button>
      </div>

      <template v-for="t in camTops" :key="t.id">
      <div v-if="camSub === t.id">
        <div class="la2-abox">
          <h3>{{ t.title }}</h3>
          <span v-html="t.desc"></span>
          <div class="la2-verdict" :class="t.verdictClass">{{ t.verdict }}</div>
        </div>
        <div v-if="extractedFrames.length" class="la2-inline-panel">
          <div class="la2-extracted-header">
            <span>📷 雙目圖像 + 點雲（三列布局）— 共 {{ extractedFrames.length }} 幀</span>
            <span v-if="extractedIdx >= 0" class="la2-ext-nav-info">{{ extractedIdx + 1 }} / {{ extractedFrames.length }} — {{ extractedFrames[extractedIdx].label }}</span>
            <div style="display:flex;gap:6px;align-items:center">
              <button class="la2-nav-btn" :disabled="extractedIdx <= 0" @click="selectExtracted(extractedIdx - 1)">◀</button>
              <button class="la2-nav-btn" :disabled="extractedIdx >= extractedFrames.length - 1" @click="selectExtracted(extractedIdx + 1)">▶</button>
            </div>
            <div class="la2-legend" style="margin:0">
              <span class="la2-li"><span class="la2-dot grass"></span>label=2 grass</span>
              <span class="la2-li"><span class="la2-dot road"></span>label=3 road</span>
              <span class="la2-li"><span class="la2-dot stat5"></span>label=5 static_obstacle</span>
              <span class="la2-li"><span class="la2-dot unk"></span>其他</span>
            </div>
          </div>
          <div class="la2-extracted-body-3col">
            <div class="la2-thumb-column">
              <div v-for="(fr, i) in extractedFrames" :key="fr.img" class="la2-ext-thumb-vertical" :class="{ active: extractedIdx === i }" @click="selectExtracted(i)">
                <img :src="extractedImgUrl(fr.img)" loading="lazy" />
                <div class="la2-lbl">{{ i + 1 }}</div>
              </div>
            </div>
            <div class="la2-extracted-img-main">
              <div v-if="extractedIdx < 0" class="la2-pcd-empty">點擊左側縮圖選擇幀</div>
              <img v-else :src="extractedImgUrl(extractedFrames[extractedIdx].img)" class="la2-ext-img-full" />
            </div>
            <div class="la2-extracted-pcd">
              <div v-if="extractedIdx < 0" class="la2-pcd-empty">選擇幀後顯示對應點雲</div>
              <div v-else class="la2-ext-pcd-canvas la2-extract-pcd-slot"></div>
            </div>
          </div>
        </div>
      </div>
      </template>

      <div v-show="camSub === 'pcd'">
        <div class="la2-abox">
          <h3>🔵 CAMERA 包 PCD 點雲可視化（label著色）</h3>
          PCD格式: ascii，欄位: x y z rgb label，共22個文件
        </div>
        <div class="la2-legend">
          <span class="la2-li"><span class="la2-dot grass"></span>label=2 grass</span>
          <span class="la2-li"><span class="la2-dot road"></span>label=3 road</span>
          <span class="la2-li"><span class="la2-dot stat5"></span>label=5 static_obstacle</span>
          <span class="la2-li"><span class="la2-dot unk"></span>其他</span>
        </div>
        <div class="la2-pcd-wrap">
          <div class="la2-pcd-list">
            <div v-for="(f, i) in CAM_PCDS" :key="f" class="la2-pcd-item" :class="{ sel: camSelPcd === f }" @click="loadCamPcd(f)">
              <div class="la2-pn">{{ f.split('_')[0].toUpperCase() }} #{{ i+1 }}</div>
              <div class="la2-ps">{{ (f.match(/pcl(\d{8}_\d{6}_\d{3})/) || [])[1] || '' }}</div>
            </div>
          </div>
          <canvas ref="camPcdCanvas" class="la2-pcd-canvas"></canvas>
        </div>
      </div>
    </div>

    <!-- Conclusion Panel -->
    <div v-if="mainTab === 'conclusion'" class="la2-panel">
      <div class="la2-verdict-main">
        <h2>❗ 綜合分析結論：確認存在系統性誤避障問題</h2>
        <p>
          兩個 rosbag 均發現感知系統將前方草地/地面誤識別為靜態障礙物(label=3 stat)，導致機器人在正常行進環境中觸發停障。<br>
          Camera 包全程 115 幀均出現前方 0.05m 大量 stat 點，機器人始終靜止，說明誤避障為持續性、系統性問題，而非偶發。<br>
          NAV 包在 4 次速度歸零停障期間，點雲前方最近點均在 0.10m 以內，label=3 佔主導，進一步確認誤避障。
        </p>
      </div>
      <div class="la2-conc-grid">
        <div class="la2-cc">
          <h3>📦 NAV 包分析結論</h3>
          <ul>
            <li>共 4 次停障，集中在 03:22:50~03:23:22</li>
            <li>Stop1 最嚴重：持續 4.62s，stat=478點@0.10m</li>
            <li>前方最近障礙距離均在 0.10m，極近</li>
            <li>label=3 stat 在草地環境中大量誤觸發</li>
            <li>感知日誌(det欄位全為0)與停障矛盾，懷疑分割輸出驅動停障</li>
            <li>系統未進行導航任務，屬測試場景誤避障</li>
          </ul>
        </div>
        <div class="la2-cc">
          <h3>📷 CAMERA 包分析結論</h3>
          <ul>
            <li>全程 115 幀均有 0.05m 極近 stat 點</li>
            <li>機器人全程靜止(odom vx=0)，非移動中誤判</li>
            <li>Top5 場景 close_stat 均在 455~491 點</li>
            <li>PCD 點雲顯示大量 label=3 點分佈在前方草地區域</li>
            <li>左右目圖像顯示前方為正常草地，無真實障礙物</li>
            <li>確認：草地/低矮植被被誤分類為 stat 障礙物</li>
          </ul>
        </div>
        <div class="la2-cc">
          <h3>🔍 根本原因分析</h3>
          <ul>
            <li>stereo_perception 分割模型對草地場景泛化不足</li>
            <li>label=3(stat) 閾值過低，草地點雲觸發靜態障礙判定</li>
            <li>前方極近距離(0.05~0.1m)未做地面過濾</li>
            <li>det欄位雖為0，但分割輸出仍傳至決策層</li>
            <li>near_obstacle_limit 規則被草地點雲觸發</li>
          </ul>
        </div>
        <div class="la2-cc">
          <h3>🔧 建議改進措施</h3>
          <ul>
            <li>增加地面點雲過濾：x&lt;0.3m 區域剔除低矮點</li>
            <li>調整 near_obstacle_limit 閾值或增加最小點數限制</li>
            <li>對 label=3 增加距離-點數雙重閾值判斷</li>
            <li>補充草地場景訓練數據，提升分割模型泛化能力</li>
            <li>增加 lown(label=1) 誤分為 stat(label=3) 的混淆矩陣監控</li>
          </ul>
        </div>
      </div>
      <div class="la2-abox" style="margin-top:8px">
        <h3>📊 停障事件詳表</h3>
        <table class="la2-table">
          <thead><tr><th>停障編號</th><th>開始時間</th><th>持續時長</th><th>前方點數</th><th>最近距離</th><th>主要標籤</th><th>判定</th></tr></thead>
          <tbody>
            <tr><td>Stop1</td><td>03:22:50</td><td style="color:#ef5350;font-weight:bold">4.62s</td><td>516</td><td>0.101m</td><td>stat=478, lown=38</td><td style="color:#ef5350">⚠ 誤避障</td></tr>
            <tr><td>Stop2</td><td>03:23:03</td><td>0.40s</td><td>1694</td><td>0.100m</td><td>stat=747, other=794, lown=153</td><td style="color:#ff9800">⚠ 可疑</td></tr>
            <tr><td>Stop3a</td><td>03:23:19</td><td>0.24s</td><td>2357</td><td>0.101m</td><td>other=1313, stat=540</td><td style="color:#ff9800">⚠ 可疑</td></tr>
            <tr><td>Stop3b</td><td>03:23:21</td><td>1.14s</td><td>2357</td><td>0.101m</td><td>other=1313, stat=540</td><td style="color:#ff9800">⚠ 可疑</td></tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Lightbox -->
    <div v-if="lbOpen" class="la2-lightbox" @click="lbOpen=false">
      <span class="la2-lb-close" @click.stop="lbOpen=false">✕</span>
      <img :src="lbSrc" @click.stop />
      <div class="la2-lb-name">{{ lbName }}</div>
    </div>

  </div>
</template>

<script setup lang="ts">
import { ref, watch, nextTick, onMounted, onBeforeUnmount } from 'vue'
import * as THREE from 'three'
import {
  createThreeScene, attachOrbitControls, updateSphCamera,
  parsePcdAscii, buildPoints,
  type SphState,
} from '../composables/usePcdRenderer'

const VIZ_DIR = 'data/visualization/0327'
const CAMERA_BAG_DIR = 'data/bag_debug/0111/0327/rosbag_LK-MR6P1US000111_camera_202603220059/bag_extract_camera'
const camBagPath = ref('data/bag_debug/0111/0327/rosbag_LK-MR6P1US000111_camera_202603220059')
const PASSABLE_LABELS = new Set([2])  // only grass dimmed; label=3(stat/road) kept bright for visibility

const navBagPath = ref('data/bag_debug/0111/0327/rosbag_LK-MR6P1US000111_navigation_202603270322')
const extracting = ref(false)
const extractType = ref<'camera' | 'nav' | ''>('')
const extractLogs = ref<string[]>([])
const extractLogVisible = ref(false)
const extractLogEl = ref<HTMLElement | null>(null)
const extractedFrames = ref<{ img: string; pcd: string; label: string }[]>([])
const extractedIdx = ref(-1)
const extractPcdCtx = ref<PcdCtx | null>(null)

// Preview state
const previewImages = ref<string[]>([])
const previewSelectedIdx = ref(-1)
const loadingPreview = ref(false)
const previewBaseDir = ref('')

async function doExtractCamera() {
  await doExtract(camBagPath.value, 'camera')
}

async function doExtractNav() {
  await doExtract(navBagPath.value, 'nav')
}

async function loadDefaultPreview() {
  loadingPreview.value = true
  previewImages.value = []
  previewSelectedIdx.value = -1

  try {
    // 尝试从nav包路径加载已提取的图片
    const navPath = navBagPath.value.trim()
    if (!navPath) {
      console.log('[loadDefaultPreview] Nav 包路徑為空，跳過加載')
      return
    }

    // 检查 bag_extract_nav/bag_extract_left 目录
    const imgDir = `${navPath}/bag_extract_nav/bag_extract_left`

    const res = await fetch('/offline/list_images', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ dir: imgDir }),
    })

    if (!res.ok) {
      console.log(`[loadDefaultPreview] 無法讀取目錄: ${imgDir}，可能尚未提取`)
      return
    }

    const data = await res.json()
    if (data.ok && data.images && data.images.length > 0) {
      previewBaseDir.value = imgDir
      previewImages.value = data.images
      previewSelectedIdx.value = 0
      console.log(`[loadDefaultPreview] 成功加載 ${data.images.length} 張圖片`)
    } else {
      console.log(`[loadDefaultPreview] 目錄中沒有找到圖片: ${imgDir}`)
    }
  } catch (e) {
    console.error(`[loadDefaultPreview] 加載預覽失敗:`, e)
  } finally {
    loadingPreview.value = false
  }
}

function getPreviewImageUrl(filename: string): string {
  return `/offline/local_file?path=${encodeURIComponent(previewBaseDir.value + '/' + filename)}`
}

async function doExtract(bagPath: string, type: 'camera' | 'nav') {
  const navPath = bagPath.trim()
  if (!navPath) { alert(`請輸入 ${type === 'camera' ? 'Camera' : 'Nav'} 包路徑`); return }
  extracting.value = true
  extractType.value = type
  extractLogVisible.value = true
  extractLogs.value = ['正在检测bag包类型...']
  try {
    // Detect whether bag has move_abnormal topic
    const infoRes = await fetch('/api/bag_topics', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ nav_bag: navPath }),
    })
    let useLeftPcl = false
    if (infoRes.ok) {
      const info = await infoRes.json()
      const hasAbnormal = (info.topics as string[]).includes('/decision_assistant/move_abnormal')
      useLeftPcl = !hasAbnormal
      extractLogs.value.push(hasAbnormal ? '检测到 move_abnormal 话题，使用避障帧提取模式' : '未检测到 move_abnormal 话题，使用单目+点云全量提取模式')
    } else {
      extractLogs.value.push('话题检测失败，默认使用全量提取模式')
      useLeftPcl = true
    }

    const endpoint = useLeftPcl ? '/api/extract_left_pcl' : '/api/extract'
    extractLogs.value.push('正在提取，請稍候...')
    const res = await fetch(endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        nav_bag: navPath,
        bag_type: type  // 传递包类型给后端
      }),
    })
    if (!res.ok) {
      extractLogs.value.push(`❌ 服務器錯誤 HTTP ${res.status}`)
      return
    }
    const data = await res.json()
    extractLogs.value.push(...(data.logs ?? []))
    if (!data.ok) {
      extractLogs.value.push('❌ 提取失敗')
    } else {
      // navPath is the bag root directory, no need to remove last component
      const bagDir = navPath
      // Camera包和Nav包使用不同的目录结构
      const extractSubDir = type === 'camera' ? 'bag_extract_camera' : 'bag_extract_nav'
      const imgSubDir = type === 'camera' ? 'bag_extract_stereo' : 'bag_extract_left'
      const imgDir = bagDir + `/${extractSubDir}/${imgSubDir}/`
      const pcdDir = bagDir + `/${extractSubDir}/bag_extract_pcd/`
      const frames: { img: string; pcd: string; label: string }[] = []
      const pcdFiles: string[] = []
      // Camera包匹配双目图片 match_XXXX，Nav包根据模式匹配
      const imgPattern = type === 'camera'
        ? /\[img\]\s+(match_\S+\.jpg)/
        : (useLeftPcl ? /\[img\]\s+(match_\S+\.jpg)/ : /\[img\]\s+(abnormal_\S+\.jpg)/)
      const pcdPattern = /\[pcd\]\s+(\S+\.pcd)/
      for (const line of (data.logs as string[])) {
        const m = line.match(imgPattern)
        if (m) {
          const stem = m[1].replace('.jpg', '')
          frames.push({ img: imgDir + m[1], pcd: pcdDir + stem + '.pcd', label: stem.substring(0, 18) })
        }
        const pcdMatch = line.match(pcdPattern)
        if (pcdMatch) {
          pcdFiles.push(pcdDir + pcdMatch[1])
        }
      }
      extractedFrames.value = frames
      // 填充点云文件列表
      if (type === 'nav') {
        navPcdFiles.value = pcdFiles
      } else if (type === 'camera') {
        // Camera包的PCD文件列表可以从frames中提取
        // 这里暂时不处理，因为Camera包已经有单独的CAM_PCDS列表
      }
      // 自动选择第一帧
      if (frames.length > 0) {
        await nextTick()
        selectExtracted(0)
      } else {
        extractedIdx.value = -1
      }
    }
  } catch (e) {
    extractLogs.value.push(`❌ 請求失敗: ${e}`)
  } finally {
    extracting.value = false
    extractType.value = ''
    await nextTick()
    if (extractLogEl.value) extractLogEl.value.scrollTop = extractLogEl.value.scrollHeight
  }
}

const mainTab = ref<'nav' | 'camera' | 'conclusion'>('nav')
const navSub = ref('stop1')
const camSub = ref('top1')

watch(mainTab, () => { disposeExtractCtx() })

const lbOpen = ref(false)
const lbSrc = ref('')
const lbName = ref('')
function openLb(src: string, name: string) { lbSrc.value = src; lbName.value = name; lbOpen.value = true }
function onKeydown(e: KeyboardEvent) { if (e.key === 'Escape') lbOpen.value = false }
onMounted(() => {
  document.addEventListener('keydown', onKeydown)
  loadNavStopFrames('stop1')
  // 填充NAV点云文件列表
  navPcdFiles.value = [
    VIZ_DIR + '/nav_pointclouds/stop1_032250_ts1774552970605196967.bin',
    VIZ_DIR + '/nav_pointclouds/stop2_032303_ts1774552983698276432.bin',
    VIZ_DIR + '/nav_pointclouds/stop3_032319_ts1774552999499319606.bin',
  ]
  // 自动加载默认预览
  loadDefaultPreview()
})
onBeforeUnmount(() => document.removeEventListener('keydown', onKeydown))

function navImgUrl(file: string) { return `/offline/local_file?path=${encodeURIComponent(VIZ_DIR + '/nav_images/' + file)}` }
function camImgUrl(file: string) { return `/offline/local_file?path=${encodeURIComponent(VIZ_DIR + '/cam_images/' + file)}` }
function camPcdUrl(file: string) { return `/offline/local_file?path=${encodeURIComponent(VIZ_DIR + '/cam_pointclouds/' + file)}` }

function extractedImgUrl(absPath: string) {
  const url = `/offline/local_file?path=${encodeURIComponent(absPath)}`
  console.log('[extractedImgUrl]', absPath, '->', url)
  return url
}

async function selectExtracted(i: number) {
  console.log('[selectExtracted] selecting frame', i)
  extractedIdx.value = i
  const fr = extractedFrames.value[i]
  console.log('[selectExtracted] frame:', fr)
  await nextTick()
  await new Promise(r => requestAnimationFrame(r))
  await new Promise(r => requestAnimationFrame(r))
  const container = document.querySelector<HTMLElement>('.la2-extract-pcd-slot')
  if (!container) {
    console.warn('[PCD] container .la2-extract-pcd-slot not found')
    return
  }
  // Check if existing canvas is still attached to this container (slot may have been re-created by v-if)
  const existingCanvas = extractPcdCtx.value?.renderer.domElement
  if (extractPcdCtx.value && existingCanvas && !container.contains(existingCanvas)) {
    // Canvas detached (sub-tab switched) — dispose and recreate
    cancelAnimationFrame(extractPcdCtx.value.animId)
    extractPcdCtx.value.orbitCleanup?.()
    extractPcdCtx.value.points?.geometry.dispose()
    if (extractPcdCtx.value.points) (extractPcdCtx.value.points.material as THREE.Material).dispose()
    extractPcdCtx.value.renderer.dispose()
    extractPcdCtx.value = null
  }
  if (!extractPcdCtx.value) {
    const canvas = document.createElement('canvas')
    canvas.style.display = 'block'
    container.innerHTML = ''
    container.appendChild(canvas)
    // Use container size for 3-column layout
    const W = Math.max(container.clientWidth || 0, 400)
    const H = Math.max(container.clientHeight || 0, 500)
    canvas.width = W
    canvas.height = H
    canvas.style.width = '100%'
    canvas.style.height = '100%'
    extractPcdCtx.value = initPcdViewer(canvas)
    console.log('[PCD] viewer initialized', W, H)
  }
  if (!extractPcdCtx.value) return
  if (!fr.pcd) {
    console.log('[PCD] no pcd path for frame', i)
    return
  }
  try {
    console.log('[PCD] fetching', fr.pcd)
    const res = await fetch(`/offline/local_file?path=${encodeURIComponent(fr.pcd)}`)
    if (!res.ok) {
      console.error('[PCD] fetch failed', res.status, fr.pcd)
      return
    }
    const text = await res.text()
    console.log('[PCD] got text length', text.length)
    loadPcdIntoCtx(extractPcdCtx.value, text)
  } catch (e) {
    console.error('[PCD] error', e)
  }
}

const navStops = [
  { id: 'stop1', label: '🔴 Stop1 03:22:50 (4.62s)', title: '🔴 Stop1 — 03:22:50 持續 4.62s（最長停障）', imgRange: '03:22:48 ~ 03:22:52，共30張', verdictClass: 'red', verdict: '⚠ 判斷：大量 stat 標籤點集中在 0.10m 極近距離，機器人速度歸零停障 4.62 秒，疑似地面/草地被誤識別為靜態障礙物', desc: '有效點數: <b>1015</b>　前方障礙區(0.1~3m): <b>516點</b>　最近點: <b>x=0.101m</b><br>標籤: <span style="color:#66bb6a">lown 38點</span>　<span style="color:#ef5350">stat 478點</span>' },
  { id: 'stop2', label: '🟠 Stop2 03:23:03 (0.40s)', title: '🟠 Stop2 — 03:23:03 持續 0.40s', imgRange: '03:23:01 ~ 03:23:05，共30張', verdictClass: 'orange', verdict: '⚠ 判斷：三種標籤混雜，前方點數最多(1694)，短暫停障可疑', desc: '有效點數: <b>3053</b>　前方障礙區: <b>1694點</b>　最近點: <b>x=0.100m</b><br>標籤: <span style="color:#66bb6a">lown 153</span>　<span style="color:#ef5350">stat 747</span>　<span style="color:#ab47bc">other 794</span>' },
  { id: 'stop3', label: '🟡 Stop3 03:23:19 (1.38s)', title: '🟡 Stop3 — 03:23:19~22 兩次短停', imgRange: '03:23:17 ~ 03:23:23，共42張', verdictClass: 'orange', verdict: '⚠ 判斷：label=5(other) 佔主導，兩次連續短停，可疑誤避障', desc: '有效點數: <b>3409</b>　前方障礙區: <b>2357點</b>　最近點: <b>x=0.101m</b><br>標籤: <span style="color:#66bb6a">lown 504</span>　<span style="color:#ef5350">stat 540</span>　<span style="color:#ab47bc">other 1313</span>' },
]

const camTops = [
  { id: 'top1', label: 'Top1 close_stat=491', title: 'Top1 — 00:59:21.300 close_stat=491點', verdictClass: 'red', verdict: '⚠ 判斷：機器人靜止時前方0.05m即出現大量stat點，確認為草地/地面誤識別', desc: '時間: <b>2026-03-22 00:59:21</b>　最近 stat 距離: <b>0.05m</b>　stat點數: <b>491</b>' },
  { id: 'top2', label: 'Top2 close_stat=484', title: 'Top2 — 00:59:32 close_stat=484點', verdictClass: 'red', verdict: '⚠ 判斷：持續性誤避障，前方草地被判定為靜態障礙', desc: '時間: <b>2026-03-22 00:59:32</b>　極近距離 stat 點數: <b>484</b>' },
  { id: 'top3', label: 'Top3 close_stat=470', title: 'Top3 — 00:59:28 close_stat=470點', verdictClass: 'red', verdict: '⚠ 判斷：持續性誤避障', desc: '時間: <b>2026-03-22 00:59:28</b>　極近距離 stat 點數: <b>470</b>' },
  { id: 'top4', label: 'Top4 close_stat=469', title: 'Top4 — 00:59:31 close_stat=469點', verdictClass: 'red', verdict: '⚠ 判斷：持續性誤避障', desc: '時間: <b>2026-03-22 00:59:31</b>　極近距離 stat 點數: <b>469</b>' },
  { id: 'top5', label: 'Top5 close_stat=455', title: 'Top5 — 00:59:17 close_stat=455點', verdictClass: 'orange', verdict: '⚠ 判斷：同等級誤避障', desc: '時間: <b>2026-03-22 00:59:17</b>　極近距離 stat 點數: <b>455</b>' },
]

const NAV_IMGS: { file: string; stop: string }[] = [
{"file":"stop1_0148_20260327_032248.jpg","stop":"stop1"},{"file":"stop1_0149_20260327_032248.jpg","stop":"stop1"},{"file":"stop1_0150_20260327_032248.jpg","stop":"stop1"},{"file":"stop1_0151_20260327_032248.jpg","stop":"stop1"},{"file":"stop1_0152_20260327_032248.jpg","stop":"stop1"},{"file":"stop1_0153_20260327_032248.jpg","stop":"stop1"},{"file":"stop1_0154_20260327_032249.jpg","stop":"stop1"},{"file":"stop1_0155_20260327_032249.jpg","stop":"stop1"},{"file":"stop1_0156_20260327_032249.jpg","stop":"stop1"},{"file":"stop1_0157_20260327_032249.jpg","stop":"stop1"},{"file":"stop1_0158_20260327_032249.jpg","stop":"stop1"},{"file":"stop1_0159_20260327_032249.jpg","stop":"stop1"},{"file":"stop1_0160_20260327_032250.jpg","stop":"stop1"},{"file":"stop1_0161_20260327_032250.jpg","stop":"stop1"},{"file":"stop1_0162_20260327_032250.jpg","stop":"stop1"},{"file":"stop1_0163_20260327_032250.jpg","stop":"stop1"},{"file":"stop1_0164_20260327_032250.jpg","stop":"stop1"},{"file":"stop1_0165_20260327_032250.jpg","stop":"stop1"},{"file":"stop1_0166_20260327_032251.jpg","stop":"stop1"},{"file":"stop1_0167_20260327_032251.jpg","stop":"stop1"},{"file":"stop1_0168_20260327_032251.jpg","stop":"stop1"},{"file":"stop1_0169_20260327_032251.jpg","stop":"stop1"},{"file":"stop1_0170_20260327_032251.jpg","stop":"stop1"},{"file":"stop1_0171_20260327_032251.jpg","stop":"stop1"},{"file":"stop1_0172_20260327_032252.jpg","stop":"stop1"},{"file":"stop1_0173_20260327_032252.jpg","stop":"stop1"},{"file":"stop1_0174_20260327_032252.jpg","stop":"stop1"},{"file":"stop1_0175_20260327_032252.jpg","stop":"stop1"},{"file":"stop1_0176_20260327_032252.jpg","stop":"stop1"},{"file":"stop1_0177_20260327_032252.jpg","stop":"stop1"},
{"file":"stop2_0226_20260327_032301.jpg","stop":"stop2"},{"file":"stop2_0227_20260327_032301.jpg","stop":"stop2"},{"file":"stop2_0228_20260327_032301.jpg","stop":"stop2"},{"file":"stop2_0229_20260327_032301.jpg","stop":"stop2"},{"file":"stop2_0230_20260327_032301.jpg","stop":"stop2"},{"file":"stop2_0231_20260327_032301.jpg","stop":"stop2"},{"file":"stop2_0232_20260327_032302.jpg","stop":"stop2"},{"file":"stop2_0233_20260327_032302.jpg","stop":"stop2"},{"file":"stop2_0234_20260327_032302.jpg","stop":"stop2"},{"file":"stop2_0235_20260327_032302.jpg","stop":"stop2"},{"file":"stop2_0236_20260327_032302.jpg","stop":"stop2"},{"file":"stop2_0237_20260327_032302.jpg","stop":"stop2"},{"file":"stop2_0238_20260327_032303.jpg","stop":"stop2"},{"file":"stop2_0239_20260327_032303.jpg","stop":"stop2"},{"file":"stop2_0240_20260327_032303.jpg","stop":"stop2"},{"file":"stop2_0241_20260327_032303.jpg","stop":"stop2"},{"file":"stop2_0242_20260327_032303.jpg","stop":"stop2"},{"file":"stop2_0243_20260327_032303.jpg","stop":"stop2"},{"file":"stop2_0244_20260327_032304.jpg","stop":"stop2"},{"file":"stop2_0245_20260327_032304.jpg","stop":"stop2"},{"file":"stop2_0246_20260327_032304.jpg","stop":"stop2"},{"file":"stop2_0247_20260327_032304.jpg","stop":"stop2"},{"file":"stop2_0248_20260327_032304.jpg","stop":"stop2"},{"file":"stop2_0249_20260327_032304.jpg","stop":"stop2"},{"file":"stop2_0250_20260327_032305.jpg","stop":"stop2"},{"file":"stop2_0251_20260327_032305.jpg","stop":"stop2"},{"file":"stop2_0252_20260327_032305.jpg","stop":"stop2"},{"file":"stop2_0253_20260327_032305.jpg","stop":"stop2"},{"file":"stop2_0254_20260327_032305.jpg","stop":"stop2"},{"file":"stop2_0255_20260327_032305.jpg","stop":"stop2"},
{"file":"stop3_0322_20260327_032317.jpg","stop":"stop3"},{"file":"stop3_0323_20260327_032317.jpg","stop":"stop3"},{"file":"stop3_0324_20260327_032317.jpg","stop":"stop3"},{"file":"stop3_0325_20260327_032317.jpg","stop":"stop3"},{"file":"stop3_0326_20260327_032317.jpg","stop":"stop3"},{"file":"stop3_0327_20260327_032317.jpg","stop":"stop3"},{"file":"stop3_0328_20260327_032318.jpg","stop":"stop3"},{"file":"stop3_0329_20260327_032318.jpg","stop":"stop3"},{"file":"stop3_0330_20260327_032318.jpg","stop":"stop3"},{"file":"stop3_0331_20260327_032318.jpg","stop":"stop3"},{"file":"stop3_0332_20260327_032318.jpg","stop":"stop3"},{"file":"stop3_0333_20260327_032318.jpg","stop":"stop3"},{"file":"stop3_0334_20260327_032319.jpg","stop":"stop3"},{"file":"stop3_0335_20260327_032319.jpg","stop":"stop3"},{"file":"stop3_0336_20260327_032319.jpg","stop":"stop3"},{"file":"stop3_0337_20260327_032319.jpg","stop":"stop3"},{"file":"stop3_0338_20260327_032319.jpg","stop":"stop3"},{"file":"stop3_0339_20260327_032319.jpg","stop":"stop3"},{"file":"stop3_0340_20260327_032320.jpg","stop":"stop3"},{"file":"stop3_0341_20260327_032320.jpg","stop":"stop3"},{"file":"stop3_0342_20260327_032320.jpg","stop":"stop3"},{"file":"stop3_0343_20260327_032320.jpg","stop":"stop3"},{"file":"stop3_0344_20260327_032320.jpg","stop":"stop3"},{"file":"stop3_0345_20260327_032320.jpg","stop":"stop3"},{"file":"stop3_0346_20260327_032321.jpg","stop":"stop3"},{"file":"stop3_0347_20260327_032321.jpg","stop":"stop3"},{"file":"stop3_0348_20260327_032321.jpg","stop":"stop3"},{"file":"stop3_0349_20260327_032321.jpg","stop":"stop3"},{"file":"stop3_0350_20260327_032321.jpg","stop":"stop3"},{"file":"stop3_0351_20260327_032321.jpg","stop":"stop3"},{"file":"stop3_0352_20260327_032322.jpg","stop":"stop3"},{"file":"stop3_0353_20260327_032322.jpg","stop":"stop3"},{"file":"stop3_0354_20260327_032322.jpg","stop":"stop3"},{"file":"stop3_0355_20260327_032322.jpg","stop":"stop3"},{"file":"stop3_0356_20260327_032322.jpg","stop":"stop3"},{"file":"stop3_0357_20260327_032322.jpg","stop":"stop3"},{"file":"stop3_0358_20260327_032323.jpg","stop":"stop3"},{"file":"stop3_0359_20260327_032323.jpg","stop":"stop3"},{"file":"stop3_0360_20260327_032323.jpg","stop":"stop3"},{"file":"stop3_0361_20260327_032323.jpg","stop":"stop3"},{"file":"stop3_0362_20260327_032323.jpg","stop":"stop3"},{"file":"stop3_0363_20260327_032323.jpg","stop":"stop3"}
]

const CAM_IMGS: { file: string; top: string }[] = [
{"file":"top1_close_stat_491_match_0017_pcl20260322_005921_300_L20260322_005921_300_R20260322_005921_300.jpg","top":"top1"},
{"file":"top1_close_stat_491_match_0018_pcl20260322_005921_467_L20260322_005921_467_R20260322_005921_467.jpg","top":"top1"},
{"file":"top1_close_stat_491_match_0019_pcl20260322_005921_634_L20260322_005921_634_R20260322_005921_634.jpg","top":"top1"},
{"file":"top1_close_stat_491_match_0020_pcl20260322_005921_967_L20260322_005921_967_R20260322_005921_967.jpg","top":"top1"},
{"file":"top2_close_stat_484_match_0063_pcl20260322_005932_134_L20260322_005932_134_R20260322_005932_134.jpg","top":"top2"},
{"file":"top2_close_stat_484_match_0064_pcl20260322_005932_300_L20260322_005932_300_R20260322_005932_300.jpg","top":"top2"},
{"file":"top2_close_stat_484_match_0065_pcl20260322_005932_634_L20260322_005932_634_R20260322_005932_634.jpg","top":"top2"},
{"file":"top2_close_stat_484_match_0066_pcl20260322_005932_800_L20260322_005932_800_R20260322_005932_800.jpg","top":"top2"},
{"file":"top2_close_stat_484_match_0067_pcl20260322_005932_967_L20260322_005932_967_R20260322_005932_967.jpg","top":"top2"},
{"file":"top3_close_stat_470_match_0046_pcl20260322_005928_134_L20260322_005928_134_R20260322_005928_134.jpg","top":"top3"},
{"file":"top3_close_stat_470_match_0047_pcl20260322_005928_467_L20260322_005928_467_R20260322_005928_467.jpg","top":"top3"},
{"file":"top3_close_stat_470_match_0048_pcl20260322_005928_634_L20260322_005928_634_R20260322_005928_634.jpg","top":"top3"},
{"file":"top3_close_stat_470_match_0049_pcl20260322_005928_800_L20260322_005928_800_R20260322_005928_800.jpg","top":"top3"},
{"file":"top3_close_stat_470_match_0050_pcl20260322_005928_967_L20260322_005928_967_R20260322_005928_967.jpg","top":"top3"},
{"file":"top4_close_stat_469_match_0058_pcl20260322_005931_134_L20260322_005931_134_R20260322_005931_134.jpg","top":"top4"},
{"file":"top4_close_stat_469_match_0059_pcl20260322_005931_300_L20260322_005931_300_R20260322_005931_300.jpg","top":"top4"},
{"file":"top4_close_stat_469_match_0060_pcl20260322_005931_467_L20260322_005931_467_R20260322_005931_467.jpg","top":"top4"},
{"file":"top4_close_stat_469_match_0061_pcl20260322_005931_800_L20260322_005931_800_R20260322_005931_800.jpg","top":"top4"},
{"file":"top4_close_stat_469_match_0062_pcl20260322_005931_967_L20260322_005931_967_R20260322_005931_967.jpg","top":"top4"},
{"file":"top5_close_stat_455_match_0003_pcl20260322_005917_134_L20260322_005917_134_R20260322_005917_134.jpg","top":"top5"},
{"file":"top5_close_stat_455_match_0004_pcl20260322_005917_300_L20260322_005917_300_R20260322_005917_300.jpg","top":"top5"},
{"file":"top5_close_stat_455_match_0005_pcl20260322_005917_634_L20260322_005917_634_R20260322_005917_634.jpg","top":"top5"}
]

const CAM_PCDS: string[] = [
"top1_close_stat_491_match_0017_pcl20260322_005921_300_L20260322_005921_300_R20260322_005921_300.pcd",
"top1_close_stat_491_match_0018_pcl20260322_005921_467_L20260322_005921_467_R20260322_005921_467.pcd",
"top1_close_stat_491_match_0019_pcl20260322_005921_634_L20260322_005921_634_R20260322_005921_634.pcd",
"top1_close_stat_491_match_0020_pcl20260322_005921_967_L20260322_005921_967_R20260322_005921_967.pcd",
"top2_close_stat_484_match_0063_pcl20260322_005932_134_L20260322_005932_134_R20260322_005932_134.pcd",
"top2_close_stat_484_match_0064_pcl20260322_005932_300_L20260322_005932_300_R20260322_005932_300.pcd",
"top2_close_stat_484_match_0065_pcl20260322_005932_634_L20260322_005932_634_R20260322_005932_634.pcd",
"top2_close_stat_484_match_0066_pcl20260322_005932_800_L20260322_005932_800_R20260322_005932_800.pcd",
"top2_close_stat_484_match_0067_pcl20260322_005932_967_L20260322_005932_967_R20260322_005932_967.pcd",
"top3_close_stat_470_match_0046_pcl20260322_005928_134_L20260322_005928_134_R20260322_005928_134.pcd",
"top3_close_stat_470_match_0047_pcl20260322_005928_467_L20260322_005928_467_R20260322_005928_467.pcd",
"top3_close_stat_470_match_0048_pcl20260322_005928_634_L20260322_005928_634_R20260322_005928_634.pcd",
"top3_close_stat_470_match_0049_pcl20260322_005928_800_L20260322_005928_800_R20260322_005928_800.pcd",
"top3_close_stat_470_match_0050_pcl20260322_005928_967_L20260322_005928_967_R20260322_005928_967.pcd",
"top4_close_stat_469_match_0058_pcl20260322_005931_134_L20260322_005931_134_R20260322_005931_134.pcd",
"top4_close_stat_469_match_0059_pcl20260322_005931_300_L20260322_005931_300_R20260322_005931_300.pcd",
"top4_close_stat_469_match_0060_pcl20260322_005931_467_L20260322_005931_467_R20260322_005931_467.pcd",
"top4_close_stat_469_match_0061_pcl20260322_005931_800_L20260322_005931_800_R20260322_005931_800.pcd",
"top4_close_stat_469_match_0062_pcl20260322_005931_967_L20260322_005931_967_R20260322_005931_967.pcd",
"top5_close_stat_455_match_0003_pcl20260322_005917_134_L20260322_005917_134_R20260322_005917_134.pcd",
"top5_close_stat_455_match_0004_pcl20260322_005917_300_L20260322_005917_300_R20260322_005917_300.pcd",
"top5_close_stat_455_match_0005_pcl20260322_005917_634_L20260322_005917_634_R20260322_005917_634.pcd"
]

function navImgsFor(stop: string) { return NAV_IMGS.filter(i => i.stop === stop) }
function camImgsFor(top: string) { return CAM_IMGS.filter(i => i.top === top) }

function disposeExtractCtx() {
  if (extractPcdCtx.value) {
    cancelAnimationFrame(extractPcdCtx.value.animId)
    extractPcdCtx.value.orbitCleanup?.()
    if (extractPcdCtx.value.points) {
      extractPcdCtx.value.points.geometry.dispose()
      ;(extractPcdCtx.value.points.material as THREE.Material).dispose()
    }
    extractPcdCtx.value.renderer.dispose()
    extractPcdCtx.value = null
  }
  const slot = document.querySelector<HTMLElement>('.la2-extract-pcd-slot')
  if (slot) slot.innerHTML = ''
}

async function loadNavStopFrames(stopId: string) {
  disposeExtractCtx()
  const imgs = navImgsFor(stopId)
  console.log('[loadNavStopFrames]', stopId, 'imgs:', imgs.length)
  extractedFrames.value = imgs.map(img => ({
    img: VIZ_DIR + '/nav_images/' + img.file,
    pcd: '',
    label: img.file.replace('20260327_', ''),
  }))
  console.log('[loadNavStopFrames] extractedFrames:', extractedFrames.value.length, extractedFrames.value[0])
  extractedIdx.value = -1
  if (imgs.length > 0) {
    await nextTick()
    selectExtracted(0)
  }
}

async function loadCamTopFrames(topId: string) {
  disposeExtractCtx()

  // 使用预设的 CAM_IMGS 列表
  const imgs = camImgsFor(topId)
  console.log('[loadCamTopFrames]', topId, 'imgs:', imgs.length)

  // 为每个图片查找对应的PCD文件
  extractedFrames.value = imgs.map(img => {
    const imgPath = VIZ_DIR + '/cam_images/' + img.file
    // PCD文件名与图片文件名相同，只是扩展名不同
    const pcdFileName = img.file.replace('.jpg', '.pcd')
    const pcdPath = VIZ_DIR + '/cam_pointclouds/' + pcdFileName
    return {
      img: imgPath,
      pcd: pcdPath,
      label: img.file.substring(0, 50),
    }
  })

  console.log('[loadCamTopFrames] extractedFrames:', extractedFrames.value.length, extractedFrames.value[0])
  extractedIdx.value = -1
  if (extractedFrames.value.length > 0) {
    await nextTick()
    selectExtracted(0)
  }
}

// NAV .bin pcd files (placeholder - list from extract output)
const navPcdFiles = ref<string[]>([])
const navSelPcd = ref('')
const camSelPcd = ref('')

// Three.js PCD viewer
const navPcdCanvas = ref<HTMLCanvasElement | null>(null)
const camPcdCanvas = ref<HTMLCanvasElement | null>(null)

interface PcdCtx {
  renderer: THREE.WebGLRenderer
  scene: THREE.Scene
  cam: THREE.PerspectiveCamera
  animId: number
  points: THREE.Points | null
  sph: SphState
  orbitCleanup: (() => void) | null
}
const navPcdCtx = ref<PcdCtx | null>(null)
const camPcdCtx = ref<PcdCtx | null>(null)

// Color map from C++ initColorMap() — RGB values divided by 255
const LA2_LABEL_COLOR: Record<number, [number, number, number]> = {
  0:   [0,       0,       200/255],  // background 蓝色
  1:   [0,       0,       200/255],  // background 蓝色
  2:   [100/255, 255/255, 102/255],  // grass 绿色
  3:   [118/255, 89/255,  0      ],  // road 褐色
  4:   [255/255, 255/255, 0      ],  // dynamic 黄色
  5:   [255/255, 0,       0      ],  // static_obstacle 红色
  6:   [255/255, 165/255, 0      ],
  7:   [255/255, 20/255,  147/255],
  8:   [0,       255/255, 255/255],
  9:   [245/255, 130/255, 48/255 ],
  10:  [0,       64/255,  128/255],
  11:  [34/255,  139/255, 34/255 ],
  12:  [255/255, 192/255, 203/255],
  13:  [138/255, 43/255,  226/255],
  100: [255/255, 0,       0      ],  // pole 橙红
  101: [255/255, 0,       0      ],  // obst 橙红
  102: [255/255, 0,       0      ],  // fixo 橙红
  103: [255/255, 0,       255/255],  // car
  104: [255/255, 0,       0      ],  // stat 红色
  105: [255/255, 255/255, 0      ],  // dyna 黄色
  106: [0,       255/255, 255/255],  // charge_station 青色
}

function la2LabelColor(label: number): [number, number, number] {
  return LA2_LABEL_COLOR[label] ?? [0.5, 0.5, 0.5]
}

function initPcdViewer(canvas: HTMLCanvasElement): PcdCtx {
  const W = canvas.width || 800, H = canvas.height || 400
  const { renderer, scene, camera } = createThreeScene(canvas, W, H)
  const sph: SphState = { theta: 0.5, phi: 0.8, radius: 3 }
  updateSphCamera(camera, sph)
  const orbitCleanup = attachOrbitControls(canvas, sph, () => updateSphCamera(camera, sph))
  const ctx: PcdCtx = { renderer, scene, cam: camera, animId: 0, points: null, sph, orbitCleanup }
  const loop = () => { ctx.animId = requestAnimationFrame(loop); renderer.render(scene, camera) }
  loop()
  return ctx
}

// Parse 4-field PCD (x y z label) — used for nav extracted PCDs
function parsePcd4Field(text: string): { pos: Float32Array; col: Float32Array } {
  const lines = text.split('\n')
  let inData = false
  const pos: number[] = [], col: number[] = []
  for (const line of lines) {
    if (line.startsWith('DATA')) { inData = true; continue }
    if (!inData) continue
    const parts = line.trim().split(/\s+/)
    if (parts.length < 4) continue
    const x = parseFloat(parts[0]), y = parseFloat(parts[1]), z = parseFloat(parts[2])
    const label = parseInt(parts[3])
    if (!isFinite(x) || !isFinite(y) || !isFinite(z)) continue
    pos.push(x, z, -y)
    const [r, g, b] = la2LabelColor(label)
    const dim = PASSABLE_LABELS.has(label) ? 0.35 : 1.0
    col.push(r * dim, g * dim, b * dim)
  }
  return { pos: new Float32Array(pos), col: new Float32Array(col) }
}

function parsePcdAuto(text: string): { pos: Float32Array; col: Float32Array } {
  // Detect FIELDS line to determine format
  const fieldsLine = text.split('\n').find(l => l.startsWith('FIELDS'))
  const fields = fieldsLine ? fieldsLine.trim().split(/\s+/).slice(1) : []
  console.log('[parsePcdAuto] FIELDS:', fields)
  if (fields.length >= 5 && fields[3] === 'rgb') {
    console.log('[parsePcdAuto] Using parsePcdAscii (5-field format with rgb)')
    return parsePcdAscii(text, la2LabelColor, PASSABLE_LABELS, 'online')
  }
  console.log('[parsePcdAuto] Using parsePcd4Field (4-field format)')
  return parsePcd4Field(text)
}

function loadPcdIntoCtx(ctx: PcdCtx, text: string) {
  console.log('[loadPcdIntoCtx] text length:', text.length)
  if (ctx.points) {
    ctx.scene.remove(ctx.points)
    ctx.points.geometry.dispose();(ctx.points.material as THREE.Material).dispose()
    ctx.points = null
  }
  const { pos, col } = parsePcdAuto(text)
  console.log('[loadPcdIntoCtx] parsed points:', pos.length / 3, 'positions:', pos.length, 'colors:', col.length)
  if (pos.length === 0) {
    console.warn('[loadPcdIntoCtx] No points parsed!')
    return
  }
  ctx.points = buildPoints(pos, col, 0.06)
  ctx.scene.add(ctx.points)
  console.log('[loadPcdIntoCtx] points added to scene')
  const n = pos.length / 3
  let cx = 0, cy = 0, cz = 0
  for (let i = 0; i < n; i++) { cx += pos[i*3]; cy += pos[i*3+1]; cz += pos[i*3+2] }
  const center = new THREE.Vector3(cx/n, cy/n, cz/n)
  console.log('[loadPcdIntoCtx] center:', center)
  updateSphCamera(ctx.cam, ctx.sph, center)
}

async function loadCamPcd(file: string) {
  camSelPcd.value = file
  if (!camPcdCtx.value && camPcdCanvas.value) {
    const c = camPcdCanvas.value
    c.width = 800; c.height = 400
    camPcdCtx.value = initPcdViewer(c)
  }
  if (!camPcdCtx.value) return
  const res = await fetch(camPcdUrl(file))
  if (!res.ok) return
  const text = await res.text()
  loadPcdIntoCtx(camPcdCtx.value, text)
}

async function loadNavPcd(file: string) {
  navSelPcd.value = file
  if (!navPcdCtx.value && navPcdCanvas.value) {
    const c = navPcdCanvas.value
    c.width = 800; c.height = 400
    navPcdCtx.value = initPcdViewer(c)
  }
  if (!navPcdCtx.value) return

  try {
    const res = await fetch(`/offline/local_file?path=${encodeURIComponent(file)}`)
    if (!res.ok) {
      console.error('[loadNavPcd] fetch failed', res.status)
      return
    }

    // Check if it's a .bin or .pcd file
    if (file.endsWith('.bin')) {
      // Parse binary point cloud file
      const buffer = await res.arrayBuffer()
      const { pos, col } = parseBinPointCloud(buffer)
      if (pos.length === 0) {
        console.warn('[loadNavPcd] No points in bin file')
        return
      }
      // Manually load into context
      if (navPcdCtx.value.points) {
        navPcdCtx.value.scene.remove(navPcdCtx.value.points)
        navPcdCtx.value.points.geometry.dispose()
        ;(navPcdCtx.value.points.material as THREE.Material).dispose()
        navPcdCtx.value.points = null
      }
      navPcdCtx.value.points = buildPoints(pos, col, 0.06)
      navPcdCtx.value.scene.add(navPcdCtx.value.points)
      const n = pos.length / 3
      let cx = 0, cy = 0, cz = 0
      for (let i = 0; i < n; i++) { cx += pos[i*3]; cy += pos[i*3+1]; cz += pos[i*3+2] }
      updateSphCamera(navPcdCtx.value.cam, navPcdCtx.value.sph, new THREE.Vector3(cx/n, cy/n, cz/n))
    } else {
      // Parse text PCD file
      const text = await res.text()
      loadPcdIntoCtx(navPcdCtx.value, text)
    }
  } catch (e) {
    console.error('[loadNavPcd] error', e)
  }
}

// Parse binary point cloud file (x, y, z, label as floats)
function parseBinPointCloud(buffer: ArrayBuffer): { pos: Float32Array; col: Float32Array } {
  const view = new DataView(buffer)
  const floatCount = buffer.byteLength / 4
  const pointCount = Math.floor(floatCount / 4) // Assume 4 floats per point: x, y, z, label

  const pos: number[] = []
  const col: number[] = []

  for (let i = 0; i < pointCount; i++) {
    const offset = i * 16 // 4 floats * 4 bytes
    const x = view.getFloat32(offset, true)
    const y = view.getFloat32(offset + 4, true)
    const z = view.getFloat32(offset + 8, true)
    const label = Math.round(view.getFloat32(offset + 12, true))

    if (!isFinite(x) || !isFinite(y) || !isFinite(z)) continue

    // Use online coordinate remapping: (x, y, z) -> (x, z, -y)
    pos.push(x, z, -y)

    const [r, g, b] = la2LabelColor(label)
    const dim = PASSABLE_LABELS.has(label) ? 0.35 : 1.0
    col.push(r * dim, g * dim, b * dim)
  }

  console.log('[parseBinPointCloud] parsed', pos.length / 3, 'points from', buffer.byteLength, 'bytes')
  return { pos: new Float32Array(pos), col: new Float32Array(col) }
}

onBeforeUnmount(() => {
  if (navPcdCtx.value) {
    cancelAnimationFrame(navPcdCtx.value.animId)
    navPcdCtx.value.orbitCleanup?.()
    navPcdCtx.value.points?.geometry.dispose()
    if (navPcdCtx.value.points) (navPcdCtx.value.points.material as THREE.Material).dispose()
    navPcdCtx.value.renderer.dispose()
  }
  if (camPcdCtx.value) {
    cancelAnimationFrame(camPcdCtx.value.animId)
    camPcdCtx.value.orbitCleanup?.()
    camPcdCtx.value.points?.geometry.dispose()
    if (camPcdCtx.value.points) (camPcdCtx.value.points.material as THREE.Material).dispose()
    camPcdCtx.value.renderer.dispose()
  }
  disposeExtractCtx()
})

</script>

<style scoped>
.la2-root { display:flex; flex-direction:column; height:100%; background:#1a1a2e; color:#e0e0e0; font-size:13px; overflow:hidden; }
.la2-input-bar { background:#0d1117; border-bottom:1px solid #1e2a3a; padding:8px 16px; display:flex; align-items:center; gap:8px; flex-wrap:wrap; flex-shrink:0; }
.la2-input-bar label { font-size:11px; color:#888; white-space:nowrap; }
.la2-path-input { flex:1; min-width:240px; background:#1a1a2e; border:1px solid #333; border-radius:4px; padding:5px 8px; color:#e0e0e0; font-size:11px; font-family:monospace; }
.la2-path-input:focus { outline:none; border-color:#4fc3f7; }
.la2-extract-btn { padding:5px 14px; background:#1b5e20; border:1px solid #388e3c; border-radius:4px; color:#a5d6a7; font-size:11px; cursor:pointer; white-space:nowrap; }
.la2-extract-btn:hover:not(:disabled) { background:#2e7d32; color:#fff; }
.la2-extract-btn:disabled { opacity:.5; cursor:not-allowed; }
.la2-extract-log { background:#050810; border-bottom:1px solid #1e2a3a; padding:6px 16px; font-size:11px; font-family:monospace; color:#69f0ae; max-height:100px; overflow-y:auto; flex-shrink:0; }
.la2-header { background:linear-gradient(135deg,#16213e,#0f3460); padding:10px 16px; border-bottom:2px solid #e94560; flex-shrink:0; }
.la2-header h1 { font-size:15px; color:#e94560; margin-bottom:8px; }
.la2-info-grid { display:grid; grid-template-columns:repeat(4,1fr); gap:8px; }
.la2-info-card { background:rgba(255,255,255,0.05); border:1px solid rgba(255,255,255,0.12); border-radius:6px; padding:8px 10px; }
.la2-info-card h3 { font-size:10px; color:#888; text-transform:uppercase; letter-spacing:.8px; margin-bottom:4px; }
.la2-val { font-size:11px; color:#bbb; line-height:1.8; }
.la2-val b { color:#4fc3f7; }
.la2-tabs { display:flex; padding:8px 16px 0; gap:5px; background:#16213e; flex-shrink:0; }
.la2-tab-btn { padding:6px 16px; border:1px solid #444; border-bottom:none; border-radius:6px 6px 0 0; background:#1a1a2e; color:#888; cursor:pointer; font-size:12px; transition:all .2s; }
.la2-tab-btn.active { background:#0f3460; color:#4fc3f7; border-color:#4fc3f7; }
.la2-tab-btn:hover:not(.active) { background:#22223a; color:#ccc; }
.la2-panel { flex:1; padding:12px 16px; overflow-y:auto; display:flex; flex-direction:column; gap:12px; min-height:0; }
.la2-sub-tabs { display:flex; gap:5px; flex-wrap:wrap; flex-shrink:0; }
.la2-sub-btn { padding:4px 12px; border:1px solid #444; border-radius:4px; background:#1a1a2e; color:#888; cursor:pointer; font-size:11px; }
.la2-sub-btn.active { background:#0f3460; color:#ff9800; border-color:#ff9800; }
.la2-sub-btn:hover:not(.active) { background:#22223a; color:#ccc; }
.la2-abox { background:rgba(15,52,96,0.4); border:1px solid #1565c0; border-radius:7px; padding:10px 14px; line-height:1.8; }
.la2-abox h3 { color:#4fc3f7; font-size:13px; margin-bottom:5px; }
.la2-verdict { margin-top:6px; padding:6px 10px; border-radius:4px; font-weight:bold; font-size:12px; }
.la2-verdict.red { background:rgba(233,69,96,.18); border-left:4px solid #e94560; color:#ff6b6b; }
.la2-verdict.orange { background:rgba(255,152,0,.15); border-left:4px solid #ff9800; color:#ffb74d; }
.la2-sec-title { font-size:11px; color:#888; text-transform:uppercase; letter-spacing:.8px; margin:2px 0 6px; border-bottom:1px solid #333; padding-bottom:3px; }
.la2-img-grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(160px,1fr)); gap:6px; }
.la2-img-card { background:#0d1117; border:2px solid #333; border-radius:6px; overflow:hidden; cursor:pointer; transition:border-color .2s; }
.la2-img-card:hover { border-color:#4fc3f7; }
.la2-img-card img { width:100%; height:100px; object-fit:cover; display:block; }
.la2-lbl { font-size:9px; color:#555; padding:2px 4px; text-align:center; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; background:#0a0e15; }
.la2-legend { display:flex; gap:12px; flex-wrap:wrap; font-size:11px; padding:4px 0; }
.la2-li { display:flex; align-items:center; gap:4px; }
.la2-dot { width:10px; height:10px; border-radius:50%; display:inline-block; }
.la2-dot.grass { background:#64ff64; } .la2-dot.road { background:#765900; } .la2-dot.stat5 { background:#ff0000; } .la2-dot.unk { background:#888; }
.la2-pcd-wrap { display:grid; grid-template-columns:220px 1fr; gap:10px; min-height:0; }
.la2-pcd-list { overflow-y:auto; max-height:400px; border:1px solid #333; border-radius:5px; background:#0d1117; }
.la2-pcd-item { padding:7px 10px; cursor:pointer; border-bottom:1px solid #1a1a2e; }
.la2-pcd-item:hover,.la2-pcd-item.sel { background:#0f3460; }
.la2-pn { font-size:10px; color:#4fc3f7; font-weight:bold; }
.la2-ps { font-size:9px; color:#666; margin-top:1px; }
.la2-pcd-empty { padding:12px; font-size:11px; color:#555; text-align:center; }
.la2-pcd-canvas { width:100%; height:400px; border:1px solid #333; border-radius:5px; background:#050810; display:block; }
.la2-verdict-main { background:rgba(233,69,96,.10); border:2px solid #e94560; border-radius:8px; padding:12px 16px; }
.la2-verdict-main h2 { color:#e94560; font-size:14px; margin-bottom:8px; }
.la2-verdict-main p { font-size:12px; color:#ccc; line-height:2; }
.la2-conc-grid { display:grid; grid-template-columns:1fr 1fr; gap:10px; }
.la2-cc { background:rgba(0,0,0,.3); border:1px solid #1565c0; border-radius:7px; padding:12px; }
.la2-cc h3 { font-size:12px; color:#4fc3f7; margin-bottom:7px; }
.la2-cc ul { list-style:none; font-size:11px; color:#bbb; line-height:2; }
.la2-cc li::before { content:'▶ '; color:#ff9800; }
.la2-table { width:100%; border-collapse:collapse; font-size:11px; margin-top:8px; }
.la2-table th { background:#0f3460; color:#4fc3f7; padding:6px 8px; text-align:left; }
.la2-table td { padding:5px 8px; border-bottom:1px solid #1e2a3a; color:#ccc; }
.la2-table tr:hover td { background:rgba(79,195,247,.07); }
.la2-lightbox { position:fixed; inset:0; background:rgba(0,0,0,.93); z-index:9999; display:flex; align-items:center; justify-content:center; flex-direction:column; gap:8px; }
.la2-lb-close { position:absolute; top:16px; right:24px; font-size:28px; color:#fff; cursor:pointer; }
.la2-lightbox img { max-width:92vw; max-height:88vh; border:2px solid #4fc3f7; border-radius:4px; }
.la2-lb-name { font-size:11px; color:#888; }
.la2-extracted-panel { flex-shrink:0; border-top:2px solid #1565c0; background:#0a0e18; }
.la2-inline-panel { border:1px solid #1565c0; border-radius:6px; background:#0a0e18; margin-top:8px; overflow:hidden; }
.la2-extracted-header { display:flex; align-items:center; gap:10px; padding:6px 14px; background:#0f1929; font-size:12px; color:#4fc3f7; flex-wrap:wrap; }
.la2-ext-nav-info { font-size:11px; color:#90caf9; font-family:monospace; }
.la2-nav-btn { padding:2px 8px; background:#1a2a4a; border:1px solid #1565c0; border-radius:3px; color:#4fc3f7; cursor:pointer; font-size:12px; }
.la2-nav-btn:disabled { opacity:.3; cursor:not-allowed; }
.la2-nav-btn:hover:not(:disabled) { background:#1e3a6a; }
.la2-thumb-strip { display:flex; gap:5px; padding:6px 10px; overflow-x:auto; overflow-y:hidden; background:#080c14; border-bottom:1px solid #1e2a3a; flex-shrink:0; }
.la2-extracted-body { display:grid; grid-template-columns:3fr 2fr; height:380px; }
.la2-extracted-body-3col { display:grid; grid-template-columns:180px 1fr 1fr; height:500px; gap:0; }
.la2-thumb-column { overflow-y:auto; overflow-x:hidden; background:#080c14; border-right:1px solid #1e2a3a; padding:6px; display:flex; flex-direction:column; gap:6px; height:100%; }
.la2-ext-thumb-vertical { flex-shrink:0; width:100%; cursor:pointer; border:2px solid #333; border-radius:4px; overflow:hidden; transition:border-color .2s; }
.la2-ext-thumb-vertical.active { border-color:#4fc3f7; }
.la2-ext-thumb-vertical:hover { border-color:#90caf9; }
.la2-ext-thumb-vertical img { width:100%; height:80px; object-fit:cover; display:block; }
.la2-extracted-img-main { overflow:hidden; display:flex; align-items:center; justify-content:center; background:#050810; border-right:1px solid #1e2a3a; height:100%; }
.la2-ext-img-full { max-width:100%; max-height:100%; object-fit:contain; display:block; }
.la2-ext-thumb { flex-shrink:0; width:80px; cursor:pointer; border:2px solid #333; border-radius:4px; overflow:hidden; transition:border-color .2s; }
.la2-ext-thumb.active { border-color:#4fc3f7; }
.la2-ext-thumb:hover { border-color:#90caf9; }
.la2-ext-thumb img { width:100%; height:50px; object-fit:cover; display:block; }
.la2-preview-section { background:#0a0e18; border:1px solid #1565c0; border-radius:6px; margin:8px 14px; overflow:hidden; }
.la2-preview-header { display:flex; align-items:center; justify-content:space-between; padding:6px 14px; background:#0f1929; font-size:12px; color:#4fc3f7; border-bottom:1px solid #1e2a3a; }
.la2-preview-info { font-size:11px; color:#90caf9; font-family:monospace; }
.la2-preview-body { display:grid; grid-template-columns:200px 1fr; height:320px; gap:0; }
.la2-preview-thumbs { overflow-y:auto; overflow-x:hidden; background:#080c14; border-right:1px solid #1e2a3a; padding:6px; display:flex; flex-direction:column; gap:6px; }
.la2-preview-thumb { flex-shrink:0; width:100%; cursor:pointer; border:2px solid #333; border-radius:4px; overflow:hidden; transition:border-color .2s; }
.la2-preview-thumb.active { border-color:#4fc3f7; box-shadow:0 0 8px rgba(79,195,247,0.5); }
.la2-preview-thumb:hover { border-color:#90caf9; }
.la2-preview-thumb img { width:100%; height:80px; object-fit:cover; display:block; background:#222; }
.la2-preview-thumb-label { font-size:9px; color:#555; padding:2px 4px; text-align:center; background:#0a0e15; }
.la2-preview-main { overflow:hidden; display:flex; align-items:center; justify-content:center; background:#050810; padding:8px; }
.la2-preview-main img { max-width:100%; max-height:100%; object-fit:contain; cursor:zoom-in; border:1px solid #333; border-radius:4px; }
.la2-extracted-pcd { position:relative; height:100%; overflow:hidden; background:#050810; }
.la2-ext-pcd-canvas { width:100%; height:100%; display:block; background:#050810; overflow:hidden; }
.la2-extract-pcd-slot { width:100%; height:100%; display:block; }
.log-err { color:#ef5350; }
</style>
