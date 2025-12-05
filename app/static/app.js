// app/static/app.js
const uploadBtn = document.getElementById('uploadBtn');
const fileInput = document.getElementById('fileInput');
const uploadStatus = document.getElementById('uploadStatus');
const processPanel = document.getElementById('processPanel');
const s3keyEl = document.getElementById('s3key');
const processBtn = document.getElementById('processBtn');
const processStatus = document.getElementById('processStatus');
const summaryArea = document.getElementById('summaryArea');
const extractionArea = document.getElementById('extractionArea');

uploadBtn.addEventListener('click', async () => {
  const file = fileInput.files[0];
  if (!file) { uploadStatus.innerText = 'Choose a file first'; return; }
  uploadStatus.innerText = 'Uploading...';
  const form = new FormData();
  form.append('file', file);
  try {
    const res = await fetch('/upload', { method: 'POST', body: form });
    const j = await res.json();
    if (res.ok) {
      uploadStatus.innerText = 'Upload complete';
      s3keyEl.innerText = j.s3_key;
      processPanel.style.display = 'block';
      summaryArea.innerText = '—';
      extractionArea.innerText = '—';
    } else {
      uploadStatus.innerText = 'Upload failed: ' + JSON.stringify(j);
    }
  } catch (e) {
    uploadStatus.innerText = 'Upload error: ' + e;
  }
});

processBtn.addEventListener('click', async () => {
  const s3key = s3keyEl.innerText;
  if (!s3key) return;
  processStatus.innerText = 'Processing (this may take 30s)...';
  try {
    const res = await fetch('/process', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ s3_key: s3key })
    });
    const j = await res.json();
    if (res.ok) {
      processStatus.innerText = 'Processing completed';
      summaryArea.innerText = j.summary || '—';
      extractionArea.innerText = JSON.stringify(j.extraction, null, 2);
    } else {
      processStatus.innerText = 'Processing failed: ' + JSON.stringify(j);
    }
  } catch (e) {
    processStatus.innerText = 'Processing error: ' + e;
  }
});
