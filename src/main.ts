// Main application entry point
// Paraphrasing Tool - UI Shell

const modes = [
  { id: 'standard', label: 'Standard', icon: '✦' },
  { id: 'fluency', label: 'Fluency', icon: '◈' },
  { id: 'formal', label: 'Formal', icon: '◆' },
  { id: 'academic', label: 'Academic', icon: '◉' },
  { id: 'simple', label: 'Simple', icon: '○' },
  { id: 'creative', label: 'Creative', icon: '✳' },
  { id: 'expand', label: 'Expand', icon: '⊕' },
  { id: 'shorten', label: 'Shorten', icon: '⊖' },
];

let activeMode = 'standard';
let inputWordCount = 0;

function updateWordCount(): void {
  const inputEl = document.getElementById('input-area') as HTMLTextAreaElement;
  const countEl = document.getElementById('word-count');
  if (!inputEl || !countEl) return;

  const text = inputEl.value.trim();
  inputWordCount = text ? text.split(/\s+/).length : 0;
  countEl.textContent = `${inputWordCount} / 10,000`;
}

function setActiveMode(modeId: string): void {
  activeMode = modeId;
  document.querySelectorAll('.mode-btn').forEach(btn => {
    btn.classList.toggle('active', btn.getAttribute('data-mode') === modeId);
  });
}

function clearInput(): void {
  const inputEl = document.getElementById('input-area') as HTMLTextAreaElement;
  if (inputEl) {
    inputEl.value = '';
    updateWordCount();
  }
}

function init(): void {
  // Mode buttons
  document.querySelectorAll('.mode-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const mode = btn.getAttribute('data-mode');
      if (mode) setActiveMode(mode);
    });
  });

  // Word count
  const inputEl = document.getElementById('input-area') as HTMLTextAreaElement;
  if (inputEl) {
    inputEl.addEventListener('input', updateWordCount);
  }

  // Clear button
  const clearBtn = document.getElementById('clear-btn');
  if (clearBtn) {
    clearBtn.addEventListener('click', clearInput);
  }

  // Strength slider label
  const slider = document.getElementById('strength-slider') as HTMLInputElement;
  const strengthLabel = document.getElementById('strength-value');
  if (slider && strengthLabel) {
    const labels = ['Fewer Changes', 'Balanced', 'More Changes'];
    slider.addEventListener('input', () => {
      strengthLabel.textContent = labels[parseInt(slider.value)];
    });
  }
}

document.addEventListener('DOMContentLoaded', init);
