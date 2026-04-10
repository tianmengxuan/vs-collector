// 报警记录页面 JS
function loadAlarms() {
  const onlyActive = document.getElementById('only-active').checked ? '1' : '0';
  fetch(`/api/alarms?active=${onlyActive}&limit=100`).then(r => r.json()).then(d => {
    const tbody = document.getElementById('alarms-body');
    if (!d.data || d.data.length === 0) {
      tbody.innerHTML = '<tr><td colspan="8" class="loading">暂无报警记录</td></tr>';
      return;
    }
    tbody.innerHTML = d.data.map(a => `
      <tr>
        <td>${a.alarm_time || '--'}</td>
        <td><code style="font-size:12px">${a.device_udid}</code></td>
        <td>CH${String(a.channel_no).padStart(2,'0')}</td>
        <td class="alarm-type-${a.alarm_type}">${a.alarm_type === 'alarm' ? '⚠️ 报警' : '⚡ 警告'}</td>
        <td>${Number(a.value).toFixed(2)}</td>
        <td>${Number(a.threshold).toFixed(2)}</td>
        <td>${a.message || '--'}</td>
        <td class="${a.is_cleared ? 'alarm-cleared' : 'alarm-active'}">${a.is_cleared ? '✅ 已消除' : '🔴 未消除'}</td>
      </tr>`).join('');
  });
}

document.addEventListener('DOMContentLoaded', loadAlarms);
