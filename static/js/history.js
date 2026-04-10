// 历史曲线页面 JS
let chartWH, chartFreq, chartPressure;

function getParams() {
  const params = new URLSearchParams(window.location.search);
  const udid = params.get('udid') || '';
  const ch = params.get('ch') || '1';
  if (udid) document.getElementById('q-udid').value = udid;
  if (ch)   document.getElementById('q-ch').value = ch;
}

function initCharts() {
  chartWH = echarts.init(document.getElementById('chart-waterhead'));
  chartFreq = echarts.init(document.getElementById('chart-freq'));
  chartPressure = echarts.init(document.getElementById('chart-pressure'));
  
  const opt = (title, unit, color) => ({
    tooltip: { trigger: 'axis', axisPointer: { type: 'cross' } },
    grid: { left: 60, right: 20, top: 30, bottom: 40 },
    xAxis: { type: 'category', data: [], axisLabel: { fontSize: 11 }, boundaryGap: false },
    yAxis: { type: 'value', name: unit, nameTextStyle: { fontSize: 12 } },
    series: [{ name: title, type: 'line', data: [], smooth: true, 
               lineStyle: { color, width: 2 },
               itemStyle: { color },
               areaStyle: { color: color + '20' },
               symbol: 'none' }],
    dataZoom: [{ type: 'inside' }, { type: 'slider', height: 20 }],
  });
  
  chartWH.setOption(opt('水头(m)', 'm', '#1a6fb5'));
  chartFreq.setOption(opt('频率(Hz)', 'Hz', '#27ae60'));
  chartPressure.setOption(opt('渗压(kPa)', 'kPa', '#e67e22'));
  
  window.addEventListener('resize', () => {
    chartWH.resize(); chartFreq.resize(); chartPressure.resize();
  });
}

function loadHistory() {
  const udid = document.getElementById('q-udid').value.trim();
  const ch   = document.getElementById('q-ch').value;
  const days = document.getElementById('q-days').value;
  
  if (!udid) { alert('请输入设备UDID'); return; }
  
  const url = `/api/history?udid=${encodeURIComponent(udid)}&ch=${ch}&days=${days}`;
  
  fetch(url).then(r => r.json()).then(d => {
    if (!d.ok) return;
    
    document.getElementById('chart-title').textContent = 
      `${d.channel_name || ('CH'+ch.padStart(2,'0'))} - ${d.channel_desc || ''}  水头曲线 (m)`;
    
    const times = d.times || [];
    
    chartWH.setOption({ xAxis: { data: times }, series: [{ data: d.water_heads }] });
    chartFreq.setOption({ xAxis: { data: times }, series: [{ data: d.freq_hzs }] });
    chartPressure.setOption({ xAxis: { data: times }, series: [{ data: d.pressures }] });
    
    // 水头图添加报警线
    chartWH.setOption({
      series: [{
        markLine: {
          silent: true,
          data: [
            { yAxis: 10, lineStyle: { color: '#f39c12', type: 'dashed' }, label: { formatter: '警告线' } },
            { yAxis: 15, lineStyle: { color: '#e74c3c', type: 'dashed' }, label: { formatter: '报警线' } },
          ]
        }
      }]
    });
    
  }).catch(e => { console.error(e); alert('查询失败'); });
}

function exportCSV() {
  const udid = document.getElementById('q-udid').value.trim();
  const ch   = document.getElementById('q-ch').value;
  const days = document.getElementById('q-days').value;
  if (!udid) { alert('请输入设备UDID'); return; }
  window.open(`/api/export/csv?udid=${encodeURIComponent(udid)}&ch=${ch}&days=${days}`);
}

document.addEventListener('DOMContentLoaded', () => {
  getParams();
  initCharts();
  
  // 如果URL里有参数，自动查询
  if (document.getElementById('q-udid').value) {
    loadHistory();
  }
});
