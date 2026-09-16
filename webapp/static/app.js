const $ = (selector) => document.querySelector(selector);
let activeJob = null;
let pollTimer = null;

function setView(view) {
  document.querySelectorAll('.view').forEach((item) => item.classList.remove('active'));
  document.querySelectorAll('.nav').forEach((item) => item.classList.remove('active'));
  $(`#${view}-view`).classList.add('active');
  $(`.nav[data-view="${view}"]`).classList.add('active');
  if (view === 'history') loadHistory();
}

function statusLabel(status) {
  return ({ queued: '等待执行', running: '正在诊断', completed: '诊断完成', failed: '诊断失败' })[status] || status;
}

function renderJob(job) {
  activeJob = job;
  $('#job-panel').classList.remove('hidden');
  $('#job-status').textContent = statusLabel(job.status);
  $('#job-url').textContent = job.url;
  $('#job-time').textContent = job.completed_at ? new Date(job.completed_at).toLocaleString('zh-CN') : '双引擎独立运行中';
  const ready = job.status === 'completed';
  $('#geo-state').textContent = ready ? '诊断完成' : job.status === 'failed' ? '执行失败' : '正在运行';
  $('#seo-state').textContent = ready ? '诊断完成' : job.status === 'failed' ? '执行失败' : '正在运行';
  if (ready) {
    $('#result-grid').classList.remove('hidden');
    $('#geo-score').textContent = job.geo.score ?? '—';
    $('#seo-score').textContent = job.seo.score ?? '—';
    $('#geo-caption').textContent = `覆盖 ${job.geo.pages ?? 0} 个代表页面；原始报告可直接查看。`;
    $('#seo-caption').textContent = '独立基础快检报告已生成；不会混入第三方流量或排名数据。';
    clearInterval(pollTimer);
  }
  if (job.status === 'failed') {
    $('#form-error').textContent = job.error || '诊断失败，请检查网址与网络后重试。';
    clearInterval(pollTimer);
  }
}

async function pollJob(id) {
  const response = await fetch(`/api/jobs/${id}`);
  if (!response.ok) return;
  renderJob(await response.json());
}

function openReport(engine) {
  if (!activeJob || activeJob.status !== 'completed') return;
  $('#report-title').textContent = engine === 'geo' ? 'GEOHub 深度诊断报告' : '页面 SEO 快检报告';
  $('#report-frame').src = `/api/jobs/${activeJob.id}/reports/${engine}`;
  $('#report-dialog').showModal();
}

function downloadReport(engine) {
  if (!activeJob || activeJob.status !== 'completed') return;
  window.location.assign(`/api/jobs/${activeJob.id}/downloads/${engine}`);
}

async function loadHistory() {
  const list = $('#history-list');
  list.textContent = '正在加载历史报告…';
  const response = await fetch('/api/jobs');
  const jobs = response.ok ? await response.json() : [];
  if (!jobs.length) { list.textContent = '还没有完成的诊断。'; return; }
  list.innerHTML = jobs.map((job) => `<article class="history-item"><div><strong>${escapeHtml(job.url)}</strong><small>${job.completed_at ? new Date(job.completed_at).toLocaleString('zh-CN') : statusLabel(job.status)}</small></div><div><small>GEOHub</small><div class="history-score">${job.geo?.score ?? '—'}</div></div><div><small>SEO 快检</small><div class="history-score">${job.seo?.score ?? '—'}</div></div><button class="secondary" data-job="${job.id}">查看报告</button></article>`).join('');
  list.querySelectorAll('[data-job]').forEach((button) => button.addEventListener('click', () => { const job = jobs.find((item) => item.id === button.dataset.job); setView('new'); renderJob(job); }));
}

function escapeHtml(value) { const node = document.createElement('span'); node.textContent = value; return node.innerHTML; }

$('#diagnosis-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  $('#form-error').textContent = '';
  const button = event.currentTarget.querySelector('button');
  button.disabled = true; button.textContent = '正在提交…';
  try {
    const response = await fetch('/api/jobs', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ url: $('#url').value.trim() }) });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || '无法创建诊断任务');
    $('#result-grid').classList.add('hidden'); renderJob(data); clearInterval(pollTimer); pollTimer = setInterval(() => pollJob(data.id), 1400); pollJob(data.id);
  } catch (error) { $('#form-error').textContent = error.message; } finally { button.disabled = false; button.textContent = '开始诊断'; }
});
document.querySelectorAll('.nav').forEach((button) => button.addEventListener('click', () => setView(button.dataset.view)));
$('#refresh-history').addEventListener('click', loadHistory);
$('#open-geo').addEventListener('click', () => openReport('geo'));
$('#open-seo').addEventListener('click', () => openReport('seo'));
$('#download-geo').addEventListener('click', () => downloadReport('geo'));
$('#download-seo').addEventListener('click', () => downloadReport('seo'));
$('#close-report').addEventListener('click', () => { $('#report-dialog').close(); $('#report-frame').src = 'about:blank'; });
