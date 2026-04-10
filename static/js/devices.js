// 设备管理页面 JS
function loadDevices() {
  fetch('/api/devices').then(r => r.json()).then(d => {
    const tbody = document.getElementById('devices-body');
    if (!d.data || d.data.length === 0) {
      tbody.innerHTML = '<tr><td colspan="5" class="loading">暂无设备记录</td></tr>';
      return;
    }
    tbody.innerHTML = d.data.map(dev => `
      <tr>
        <td><code>${dev.udid}</code></td>
        <td>${dev.name || '<span style="color:#999">未命名</span>'}</td>
        <td>${dev.location || '<span style="color:#999">未设置</span>'}</td>
        <td>${dev.last_seen || '--'}</td>
        <td>
          <button class="btn btn-outline btn-sm" onclick="editDevice('${dev.udid}', '${escHtml(dev.name||'')}', '${escHtml(dev.location||'')}')">编辑</button>
          <button class="btn btn-outline btn-sm" onclick="viewHistory('${dev.udid}')">历史</button>
        </td>
      </tr>`).join('');
  });
}

function escHtml(s) { return String(s).replace(/'/g, "\\'"); }

function editDevice(udid, name, loc) {
  document.getElementById('edit-udid').value = udid;
  document.getElementById('edit-name').value = name;
  document.getElementById('edit-location').value = loc;
  document.getElementById('edit-modal').style.display = 'flex';
}

function closeModal() {
  document.getElementById('edit-modal').style.display = 'none';
}

function saveDevice() {
  const udid = document.getElementById('edit-udid').value;
  const name = document.getElementById('edit-name').value.trim();
  const location = document.getElementById('edit-location').value.trim();
  
  fetch(`/api/devices/${encodeURIComponent(udid)}`, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({name, location}),
  }).then(r => r.json()).then(d => {
    if (d.ok) { closeModal(); loadDevices(); }
    else alert('保存失败');
  });
}

function viewHistory(udid) {
  window.location.href = `/history?udid=${encodeURIComponent(udid)}&ch=1`;
}

document.addEventListener('DOMContentLoaded', loadDevices);
