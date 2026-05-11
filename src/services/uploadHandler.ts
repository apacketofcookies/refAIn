// uploadHandler.ts
// Handles CSV file upload, modal preview, and CSV analysis

const API_URL = 'https://refain-ai-dataset-cleaner.onrender.com/analyze/';
const PREVIEW_LIMIT = 100; // maximum rows to render in the preview to avoid slow DOM rendering
const MAX_FILE_SIZE_MB = 10; // maximum file size in MB
const MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024;

function parseCSV(text: string, maxRows = Infinity): string[][] {
  const lines = text.trim().split('\n');
  const rows: string[][] = [];

  for (let r = 0; r < lines.length; r++) {
    if (rows.length > maxRows) break;

    const row = lines[r];
    const cells: string[] = [];
    let current = '';
    let inQuotes = false;

    for (let i = 0; i < row.length; i++) {
      const char = row[i];
      if (char === '"') {
        inQuotes = !inQuotes;
      } else if (char === ',' && !inQuotes) {
        cells.push(current.trim());
        current = '';
      } else {
        current += char;
      }
    }
    cells.push(current.trim());
    rows.push(cells);
  }

  return rows;
}

function createModal(rows: string[][], totalRows?: number): HTMLElement {
  const overlay = document.createElement('div');
  overlay.id = 'csv-modal-overlay';
  overlay.innerHTML = `
    <div class="csv-modal">

      <div class="csv-modal-header">
        <div class="csv-modal-title">
          <i data-lucide="table-2"></i>
          <span>CSV Preview</span>
        </div>
        <div class="csv-modal-meta">${Math.max(0, (totalRows ?? rows.length) - 1)} rows · ${rows[0]?.length ?? 0} columns${(totalRows ?? rows.length) > rows.length ? ' · Previewing first ' + (rows.length - 1) + ' rows' : ''}</div>
        <button class="csv-modal-close" id="csv-modal-close">
          <i data-lucide="x"></i>
        </button>
      </div>

      <div class="csv-modal-body">
        <div class="csv-table-wrap">
          <table class="csv-table">
            <thead>
              <tr>
                ${rows[0]?.map(h => `<th>${h}</th>`).join('') ?? ''}
              </tr>
            </thead>
            <tbody>
              ${rows
                .slice(1)
                .map(
                  row => `<tr>${row.map(cell => `<td>${cell}</td>`).join('')}</tr>`
                )
                .join('')}
            </tbody>
          </table>
        </div>
      </div>

      <div class="csv-modal-footer">
        <span class="csv-filename" id="csv-filename"></span>
        <div class="csv-modal-footer-actions">
          <button class="csv-modal-cancel" id="csv-modal-cancel">Close</button>
          <button class="csv-modal-action" id="csv-modal-action">Analyze CSV</button>
        </div>
      </div>

    </div>
  `;
  return overlay;
}

function injectStyles(): void {
  if (document.getElementById('csv-modal-styles')) return;

  const style = document.createElement('style');
  style.id = 'csv-modal-styles';
  style.textContent = `
    #csv-modal-overlay {
      position: fixed;
      inset: 0;
      background: rgba(0, 0, 0, 0.6);
      backdrop-filter: blur(6px);
      z-index: 1000;
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 24px;
      animation: csvOverlayIn 0.2s ease both;
    }

    @keyframes csvOverlayIn {
      from { opacity: 0; }
      to   { opacity: 1; }
    }

    .csv-modal {
      background: #13161e;
      border: 1px solid #2a2f3f;
      border-radius: 16px;
      width: 100%;
      max-width: 820px;
      max-height: 80vh;
      display: flex;
      flex-direction: column;
      overflow: hidden;
      animation: csvModalIn 0.25s cubic-bezier(0.34, 1.56, 0.64, 1) both;
      box-shadow: 0 24px 80px rgba(0, 0, 0, 0.5);
    }

    @keyframes csvModalIn {
      from { opacity: 0; transform: translateY(16px) scale(0.97); }
      to   { opacity: 1; transform: translateY(0) scale(1); }
    }

    .csv-modal-header {
      display: flex;
      align-items: center;
      gap: 12px;
      padding: 18px 22px;
      border-bottom: 1px solid #2a2f3f;
      background: #1a1e28;
      flex-shrink: 0;
    }

    .csv-modal-title {
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 14px;
      font-weight: 600;
      color: #e8ecf4;
      flex: 1;
    }

    .csv-modal-title i {
      width: 16px;
      height: 16px;
      color: #6c8aff;
    }

    .csv-modal-meta {
      font-size: 12px;
      color: #525a72;
      font-family: 'DM Mono', monospace;
    }

    .csv-modal-close {
      background: transparent;
      border: none;
      color: #525a72;
      cursor: pointer;
      padding: 4px;
      border-radius: 6px;
      display: flex;
      align-items: center;
      justify-content: center;
      transition: all 0.15s;
    }

    .csv-modal-close:hover {
      color: #e8ecf4;
      background: #222736;
    }

    .csv-modal-close i {
      width: 16px;
      height: 16px;
    }

    .csv-modal-body {
      flex: 1;
      overflow: auto;
      padding: 0;
    }

    .csv-table-wrap {
      min-width: 100%;
      overflow-x: auto;
    }

    .csv-table {
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
    }

    .csv-table thead tr {
      background: #1a1e28;
      position: sticky;
      top: 0;
      z-index: 1;
    }

    .csv-table th {
      padding: 12px 16px;
      text-align: left;
      font-size: 11px;
      font-weight: 600;
      letter-spacing: 0.6px;
      text-transform: uppercase;
      color: #6c8aff;
      border-bottom: 1px solid #2a2f3f;
      white-space: nowrap;
    }

    .csv-table td {
      padding: 10px 16px;
      color: #8891a9;
      border-bottom: 1px solid #1a1e28;
      max-width: 260px;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }

    .csv-table tbody tr:hover td {
      background: #1a1e28;
      color: #e8ecf4;
    }

    .csv-table tbody tr:last-child td {
      border-bottom: none;
    }

    .csv-modal-footer {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 14px 22px;
      border-top: 1px solid #2a2f3f;
      background: #1a1e28;
      flex-shrink: 0;
    }

    .csv-filename {
      font-size: 12px;
      color: #525a72;
      font-family: 'DM Mono', monospace;
    }

    .csv-modal-footer-actions {
      display: flex;
      align-items: center;
      gap: 10px;
    }

    .csv-modal-cancel {
      background: transparent;
      border: 1px solid #2a2f3f;
      color: #8891a9;
      font-family: 'Sora', sans-serif;
      font-size: 13px;
      font-weight: 500;
      padding: 7px 18px;
      border-radius: 8px;
      cursor: pointer;
      transition: all 0.15s;
    }

    .csv-modal-cancel:hover {
      border-color: #343a50;
      color: #e8ecf4;
    }

    .csv-modal-action {
      background: linear-gradient(135deg, #6c8aff, #a78bfa);
      border: none;
      color: #fff;
      font-family: 'Sora', sans-serif;
      font-size: 13px;
      font-weight: 600;
      padding: 7px 18px;
      border-radius: 8px;
      cursor: pointer;
      transition: all 0.15s;
      box-shadow: 0 4px 18px rgba(108, 138, 255, 0.28);
    }

    .csv-modal-action:hover:not(:disabled) {
      transform: translateY(-1px);
      box-shadow: 0 8px 24px rgba(108, 138, 255, 0.38);
    }

    .csv-modal-action:disabled {
      opacity: 0.7;
      cursor: wait;
      transform: none;
    }
  `;
  document.head.appendChild(style);
}

function closeModal(): void {
  const overlay = document.getElementById('csv-modal-overlay');
  if (overlay) overlay.remove();
}

function showParsingOverlay(): void {
  if (document.getElementById('csv-parsing-overlay')) return;
  const ov = document.createElement('div');
  ov.id = 'csv-parsing-overlay';
  ov.style.position = 'fixed';
  ov.style.inset = '0';
  ov.style.display = 'flex';
  ov.style.alignItems = 'center';
  ov.style.justifyContent = 'center';
  ov.style.zIndex = '1001';
  ov.innerHTML = `<div style="background:#13161e;padding:18px 22px;border-radius:12px;border:1px solid #2a2f3f;color:#e8ecf4;font-weight:600">Parsing CSV…</div>`;
  document.body.appendChild(ov);
}

function hideParsingOverlay(): void {
  const ov = document.getElementById('csv-parsing-overlay');
  if (ov) ov.remove();
}

function showAnalysisOverlay(): void {
  if (document.getElementById('csv-analysis-overlay')) return;
  const ov = document.createElement('div');
  ov.id = 'csv-analysis-overlay';
  ov.style.position = 'fixed';
  ov.style.inset = '0';
  ov.style.display = 'flex';
  ov.style.alignItems = 'center';
  ov.style.justifyContent = 'center';
  ov.style.zIndex = '1001';
  ov.style.background = 'rgba(0, 0, 0, 0.7)';
  ov.innerHTML = `<div style="background:#13161e;padding:24px 32px;border-radius:12px;border:1px solid #2a2f3f;color:#e8ecf4;text-align:center;"><div style="font-weight:600;margin-bottom:12px;">Analyzing dataset...</div><div style="font-size:12px;color:#8891a9;">This may take a moment depending on file size.</div></div>`;
  document.body.appendChild(ov);
}

function hideAnalysisOverlay(): void {
  const ov = document.getElementById('csv-analysis-overlay');
  if (ov) ov.remove();
}

function renderAnalysisResult(result: unknown): void {
  const outputPlaceholder = document.querySelector('.output-placeholder') as HTMLElement | null;
  if (!outputPlaceholder) return;

  outputPlaceholder.innerHTML = '';
  outputPlaceholder.style.pointerEvents = 'auto';

  const res: any = result as any;
  const cleanedText = (res && (res.fixed_text || res.cleaned_csv)) ? String(res.fixed_text || res.cleaned_csv) : '';

  const pre = document.createElement('pre');
  pre.style.color = '#e8ecf4';
  pre.style.padding = '20px';
  pre.style.margin = '0';
  pre.style.whiteSpace = 'pre-wrap';
  pre.style.wordBreak = 'break-word';
  pre.textContent = cleanedText || JSON.stringify(result, null, 2);
  outputPlaceholder.appendChild(pre);

  const actions = document.createElement('div');
  actions.style.display = 'flex';
  actions.style.gap = '8px';
  actions.style.padding = '10px 20px';

  function makeActionButton(label: string, onClick: () => void) {
    const btn = document.createElement('button');
    btn.className = 'csv-modal-action';
    btn.textContent = label;
    btn.addEventListener('click', onClick);
    return btn;
  }

  if (cleanedText) {
    try {
      (window as any).lastCleanedCsv = cleanedText;
      const evt = new CustomEvent('cleanedCsvReady', { detail: { size: cleanedText.length } });
      window.dispatchEvent(evt);
    } catch (e) {
      // ignore if environment doesn't allow writing to window
    }
    actions.appendChild(
      makeActionButton('Copy cleaned text', () => {
        void navigator.clipboard.writeText(cleanedText);
      })
    );

    actions.appendChild(
      makeActionButton('Download cleaned CSV', () => {
        const blob = new Blob([cleanedText], { type: 'text/csv;charset=utf-8;' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = 'cleaned.csv';
        document.body.appendChild(a);
        a.click();
        a.remove();
        URL.revokeObjectURL(url);
      })
    );
  }

  if (actions.children.length) outputPlaceholder.appendChild(actions);
}

async function analyzeCSVFile(
  file: File | null,
  rows: string[][],
  rawText: string = ''
): Promise<void> {

  const actionBtn = document.getElementById('csv-modal-action') as HTMLButtonElement | null;

  if (actionBtn) {
    actionBtn.disabled = true;
    actionBtn.textContent = 'Analyzing...';
  }

  showAnalysisOverlay();

  const timeoutMs = 90000;

  const abortController = new AbortController();

  const timeoutHandle = setTimeout(() => {
    abortController.abort();
  }, timeoutMs);

  try {

    const formData = new FormData();

    // -------------------------
    // Send the decoded CSV text for both uploads and pasted data.
    // This keeps file uploads on the same analysis path as pasted CSV text.
    const csvText = rawText || rows.map(row => row.join(',')).join('\n');
    formData.append('text', csvText);

    const response = await fetch(API_URL, {
      method: 'POST',
      body: formData,
      signal: abortController.signal,
    });

    clearTimeout(timeoutHandle);

    if (!response.ok) {

      let errPayload: any = {
        error: 'Server error',
        details: response.statusText
      };

      try {
        errPayload = await response.json();
      } catch {}

      hideAnalysisOverlay();

      renderAnalysisResult(errPayload);

      return;
    }

    const data = await response.json();

    console.log("BACKEND RESPONSE:", data);

    hideAnalysisOverlay();

    renderAnalysisResult(data);

    closeModal();

  } catch (error) {

    clearTimeout(timeoutHandle);

    hideAnalysisOverlay();

    const errMsg =
      error instanceof Error && error.name === 'AbortError'
        ? 'Analysis timed out.'
        : String(error);

    renderAnalysisResult({
      error: 'Analysis failed',
      details: errMsg
    });

    console.error(error);

  } finally {

    if (actionBtn) {
      actionBtn.disabled = false;
      actionBtn.textContent = 'Analyze CSV';
    }
  }
}

function showCSVModal(rows: string[][], filename: string, totalRows?: number, file: File | null = null, rawText: string = ''): void {
  injectStyles();

  const existing = document.getElementById('csv-modal-overlay');
  if (existing) existing.remove();

  const modal = createModal(rows, totalRows);
  document.body.appendChild(modal);

  // Set filename
  const filenameEl = document.getElementById('csv-filename');
  if (filenameEl) filenameEl.textContent = filename;

  // Re-init lucide icons inside modal
  if ((window as any).lucide) {
    (window as any).lucide.createIcons();
  }

  // Close handlers
  document.getElementById('csv-modal-close')?.addEventListener('click', closeModal);
  document.getElementById('csv-modal-cancel')?.addEventListener('click', closeModal);
  document.getElementById('csv-modal-action')?.addEventListener('click', () => {
    void analyzeCSVFile(file, rows, rawText);
  });
  modal.addEventListener('click', (e) => {
    if (e.target === modal) closeModal();
  });

  // Esc key
  const onKeyDown = (e: KeyboardEvent) => {
    if (e.key === 'Escape') {
      closeModal();
      document.removeEventListener('keydown', onKeyDown);
    }
  };
  document.addEventListener('keydown', onKeyDown);
}

export function initUploadHandler(): void {
  const uploadBtn = document.querySelector<HTMLButtonElement>('button[title="Upload file"]');
  if (!uploadBtn) return;

  // Hidden file input
  const fileInput = document.createElement('input');
  fileInput.type = 'file';
  fileInput.accept = '.csv';
  fileInput.style.display = 'none';
  document.body.appendChild(fileInput);

  uploadBtn.addEventListener('click', () => fileInput.click());

  fileInput.addEventListener('change', () => {
    const file = fileInput.files?.[0];
    if (!file) return;

    if (!file.name.endsWith('.csv')) {
      alert('Please upload a .csv file only.');
      return;
    }

    if (file.size > MAX_FILE_SIZE_BYTES) {
      alert(`File size exceeds ${MAX_FILE_SIZE_MB}MB limit. Current size: ${(file.size / 1024 / 1024).toFixed(2)}MB`);
      fileInput.value = '';
      return;
    }

    const reader = new FileReader();
    reader.onload = (e) => {
      const text = e.target?.result as string;
      const totalRows = text.trim() ? text.trim().split('\n').length : 0;

      showParsingOverlay();

      // Let the spinner render before heavy parsing
      setTimeout(() => {
        const rows = parseCSV(text, PREVIEW_LIMIT + 1); // +1 for header

        hideParsingOverlay();

        if (rows.length === 0) {
          alert('The CSV file appears to be empty.');
          return;
        }

        showCSVModal(rows, file.name, totalRows, file, text);
      }, 16);
    };
    reader.readAsText(file);

    // Reset so same file can be re-uploaded
    fileInput.value = '';
  });
}