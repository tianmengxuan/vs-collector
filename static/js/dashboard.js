// 实时数据看板 JS
const REFRESH_INTERVAL = 10000;  // 10秒刷新

let statsTimer, dataTimer;

function fmtNum(v, digits=2) {
  if (v == null || v === '') return '--';
  return Number(v).toFixed(digits);
}

function loadStats() {
  fetch('/api/stats').then(r => r.json()).then(d => {
    if (!d.ok) return;
    document.getElementById('s-devices').textContent = d.total_devices;
    document.getElementById('s-records').textContent = d.total_records.toLocaleString();
    document.getElementById('s-alarms').textContent = d.active_alarms;
    const t = d.last_data_time;
    document.getElementById('s-lastdata').textContent = t ? t.substring(5, 16) : '--';
  }).catch(() => {});
}

function loadLatest() {
  fetch('/api/latest').then(r => r.json()).then(d => {
    if (!d.ok) return;
    
    const statusDot = document.getElementById('conn-status');
    const timeEl = document.getElementById('server-time');
    if (d.server_time) {
      timeEl.textContent = d.server_time;
      statusDot.className = 'status-dot online';
    }
    
    const container = document.getElementById('device-cards');
    const noData = document.getElementById('no-data');
    
    if (!d.data || d.data.length === 0) {
      container.innerHTML = '';
      noData.style.display = '';
      return;
    }
    noData.style.display = 'none';
    
    // 渲染每个设备
    container.innerHTML = d.data.map(dev => renderDevice(dev)).join('');
  }).catch(() => {
    document.getElementById('conn-status').className = 'status-dot error';
  });
}

function renderDevice(dev) {
  const chHtml = dev.channels.map(ch => renderChannel(ch, dev.udid)).join('');
  const sigBars = Math.round((dev.signal || 0) / 5);  // 0~31 映射到 0~6
  const sigIcon = '📶';
  
  return `
  <div class="device-section">
    <div class="device-header">
      <div>
        <h3>${escHtml(dev.name || dev.udid)}</h3>
        <div class="device-meta">UDID: ${dev.udid} &nbsp;|&nbsp; 位置: ${escHtml(dev.location || '未设置')}</div>
        <div class="device-meta">采集时间: ${dev.record_time || '--'}</div>
      </div>
      <div class="device-info-badges">
        <span class="badge">🔋 ${fmtNum(dev.battery_v)}V</span>
        <span class="badge">${sigIcon} ${dev.signal || 0}</span>
        <span class="badge">🌡 ${fmtNum(dev.device_temp, 1)}℃</span>
      </div>
    </div>
    <div class="device-channels">
      <div class="channels-grid">${chHtml || '<div style="padding:16px;color:#999">无通道数据</div>'}</div>
    </div>
  </div>`;
}

function renderChannel(ch, udid) {
  const h = ch.water_head_m;
  let cls = '';
  let alarmBadge = '';
  if (h != null) {
    if (Math.abs(h) >= 15) { cls = 'alarm'; alarmBadge = '<span class="ch-alarm-badge">报警</span>'; }
    else if (Math.abs(h) >= 10) { cls = 'warning'; alarmBadge = '<span class="ch-alarm-badge" style="background:#f39c12">警告</span>'; }
  }
  
  return `
  <div class="ch-cell ${cls}" onclick="goHistory('${udid}', ${ch.ch_no})" title="点击查看历史曲线">
    ${alarmBadge}
    <div class="ch-name">${escHtml(ch.name || 'CH' + String(ch.ch_no).padStart(2,'0'))}</div>
    <div class="ch-water-head">${h != null ? fmtNum(h, 2) : '--'}<span class="unit"> m</span></div>
    <div class="ch-detail">
      频率: ${ch.freq_hz != null ? fmtNum(ch.freq_hz, 1) : '--'} Hz &nbsp;
      渗压: ${ch.pressure_kpa != null ? fmtNum(ch.pressure_kpa, 1) : '--'} kPa
    </div>
    ${ch.desc ? `<div class="ch-detail" style="color:#999">${escHtml(ch.desc)}</div>` : ''}
  </div>`;
}

function goHistory(udid, chNo) {
  window.location.href = `/history?udid=${encodeURIComponent(udid)}&ch=${chNo}`;
}

function escHtml(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

// 初始化
document.addEventListener('DOMContentLoaded', () => {
  loadStats();
  loadLatest();
  statsTimer = setInterval(loadStats, 30000);
  dataTimer = setInterval(loadLatest, REFRESH_INTERVAL);
});
