// Tauri API imports
const { invoke } = window.__TAURI__.core;
const { open, save } = window.__TAURI__.dialog;
const { openPath } = window.__TAURI__.opener;

// State variables
let selectedImagePath = null;
let currentMode = 'baseplate';
let currentStuds = 'with';
let currentRing = 'none';

let imageAspectRatio = 1.0;
let isProportionsLocked = true;
let currentWidth = 0.0;
let currentHeight = 40.0;
let currentThickness = 5.5;

// DOM elements
const dropzone = document.getElementById('dropzone');
const fileNameEl = document.getElementById('file-name');
const filePathEl = document.getElementById('file-path');
const convertBtn = document.getElementById('convert-btn');
const imagePreview = document.getElementById('image-preview');
const placeholderText = document.getElementById('placeholder-text');
const previewPlaceholder = document.getElementById('preview-placeholder');

const statusIcon = document.getElementById('status-icon');
const statusSpinner = document.getElementById('status-spinner');
const statusMessage = document.getElementById('status-message');
const statusLog = document.getElementById('status-log');

const inputDimX = document.getElementById('input-dim-x');
const inputDimY = document.getElementById('input-dim-y');
const inputDimZ = document.getElementById('input-dim-z');

const statStudGrid = document.getElementById('stat-stud-grid');
const statStudCount = document.getElementById('stat-stud-count');
const recentExportsList = document.getElementById('recent-exports-list');

// Help compute dimensions proportionally and update UI
function updateStatsAndFields() {
  if (document.activeElement !== inputDimX) inputDimX.value = currentWidth.toFixed(2);
  if (document.activeElement !== inputDimY) inputDimY.value = currentHeight.toFixed(2);
  if (document.activeElement !== inputDimZ) inputDimZ.value = currentThickness.toFixed(2);

  // Stud calculations
  const numStudsX = Math.max(1, Math.floor((currentWidth - 4.9) / 8) + 1);
  const numStudsY = Math.max(1, Math.floor((currentHeight - 4.9) / 8) + 1);

  statStudGrid.textContent = `${numStudsX} x ${numStudsY}`;
  statStudCount.textContent = `${numStudsX * numStudsY} studs`;
}

function handleDimensionChange(changedField, newValue) {
  if (isNaN(newValue) || newValue <= 0) return;

  if (isProportionsLocked) {
    let ratio = 1.0;
    if (changedField === 'x') {
      ratio = newValue / currentWidth;
      currentWidth = newValue;
      currentHeight = currentHeight * ratio;
      currentThickness = currentThickness * ratio;
    } else if (changedField === 'y') {
      ratio = newValue / currentHeight;
      currentHeight = newValue;
      currentWidth = currentWidth * ratio;
      currentThickness = currentThickness * ratio;
    } else if (changedField === 'z') {
      ratio = newValue / currentThickness;
      currentThickness = newValue;
      currentWidth = currentWidth * ratio;
      currentHeight = currentHeight * ratio;
    }
  } else {
    if (changedField === 'x') currentWidth = newValue;
    else if (changedField === 'y') currentHeight = newValue;
    else if (changedField === 'z') currentThickness = newValue;
  }

  updateStatsAndFields();
}

function setupDimensionInput(inputEl, fieldName) {
  inputEl.addEventListener('input', () => {
    const val = parseFloat(inputEl.value);
    if (!isNaN(val) && val > 0) {
      handleDimensionChange(fieldName, val);
    }
  });

  inputEl.addEventListener('blur', () => {
    const val = parseFloat(inputEl.value);
    if (isNaN(val) || val <= 0) {
      inputEl.value = (fieldName === 'x' ? currentWidth : (fieldName === 'y' ? currentHeight : currentThickness)).toFixed(2);
    } else {
      inputEl.value = val.toFixed(2);
    }
  });

  inputEl.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      inputEl.blur();
    }
  });
}

// Bind lock toggle logic
window.toggleProportionsLock = function() {
  isProportionsLocked = !isProportionsLocked;
  const btn = document.getElementById('lock-proportions-btn');
  const icon = document.getElementById('lock-icon');
  const text = btn.querySelector('span');

  if (isProportionsLocked) {
    btn.className = 'flex items-center gap-1.5 px-2 py-0.5 text-[12px] font-medium rounded-md border transition-all bg-[#1C2128] border-primary text-primary';
    icon.className = 'bi bi-link-45deg';
    text.textContent = 'Linked';
    
    // Resynchronize height/thickness to match width aspect ratio when re-locked
    if (currentWidth > 0 && imageAspectRatio > 0) {
      const newWidth = currentHeight * imageAspectRatio;
      const ratio = newWidth / currentWidth;
      currentWidth = newWidth;
      currentThickness = currentThickness * ratio;
      updateStatsAndFields();
    }
  } else {
    btn.className = 'flex items-center gap-1.5 px-2 py-0.5 text-[12px] font-medium rounded-md border transition-all bg-[#161B22] border-border text-textSecondary hover:text-textMain';
    icon.className = 'bi bi-unlink';
    text.textContent = 'Independent';
  }
};

// Initialize the inputs
setupDimensionInput(inputDimX, 'x');
setupDimensionInput(inputDimY, 'y');
setupDimensionInput(inputDimZ, 'z');

// Initialize layout decoration grid
function buildPlaceholderGrid() {
  previewPlaceholder.innerHTML = '';
  for (let i = 0; i < 48; i++) {
    const cell = document.createElement('div');
    cell.className = 'border-r border-b border-[#30363D]/10 h-full w-full';
    previewPlaceholder.appendChild(cell);
  }
}
buildPlaceholderGrid();

// Initialize recent exports on load
updateRecentExportsUI();

// Option togglers
window.setMode = function(mode) {
  currentMode = mode;
  updateSegmentedControl('mode-baseplate', mode === 'baseplate');
  updateSegmentedControl('mode-brick', mode === 'brick');
};

window.setStuds = function(studs) {
  currentStuds = studs;
  updateSegmentedControl('studs-with', studs === 'with');
  updateSegmentedControl('studs-none', studs === 'none');
};

window.setRing = function(ring) {
  currentRing = ring;
  updateSegmentedControl('ring-none', ring === 'none');
  updateSegmentedControl('ring-add', ring === 'add');
};

function updateSegmentedControl(id, isActive) {
  const el = document.getElementById(id);
  if (isActive) {
    el.className = 'flex-1 py-1.5 text-center text-[13px] font-semibold rounded-md transition-all segmented-btn-active bg-[#1C2128] border border-[#30363D] text-[#F8FAFC] shadow-sm';
  } else {
    el.className = 'flex-1 py-1.5 text-center text-[13px] font-semibold rounded-md transition-all segmented-btn-inactive text-[#94A3B8] hover:text-[#F8FAFC]';
  }
}

// Reset application to default state
window.resetApp = function() {
  selectedImagePath = null;
  currentMode = 'baseplate';
  currentStuds = 'with';
  currentRing = 'none';

  imageAspectRatio = 1.0;
  isProportionsLocked = true;
  currentWidth = 0.0;
  currentHeight = 40.0;
  currentThickness = 5.5;

  // Reset lock toggle button UI
  const lockBtn = document.getElementById('lock-proportions-btn');
  const lockIcon = document.getElementById('lock-icon');
  const lockText = lockBtn.querySelector('span');
  if (lockBtn && lockIcon && lockText) {
    lockBtn.className = 'flex items-center gap-1.5 px-2 py-0.5 text-[12px] font-medium rounded-md border transition-all bg-[#1C2128] border-primary text-primary';
    lockIcon.className = 'bi bi-link-45deg';
    lockText.textContent = 'Linked';
  }

  setMode('baseplate');
  setStuds('with');
  setRing('none');

  fileNameEl.textContent = 'Drag & drop image or click to browse';
  filePathEl.textContent = 'PNG, JPG, JPEG, or BMP';
  filePathEl.className = 'text-[13px] text-textSecondary mt-1 truncate max-w-full px-2 font-mono';
  
  imagePreview.src = '';
  imagePreview.classList.add('hidden');
  placeholderText.classList.remove('hidden');

  convertBtn.setAttribute('disabled', 'true');
  convertBtn.innerHTML = '<i class="bi bi-play-fill text-lg"></i> Generate STL';

  statusIcon.innerHTML = `<i class="bi bi-circle"></i>`;
  statusIcon.className = 'text-textSecondary';
  statusSpinner.classList.add('hidden');
  statusMessage.textContent = 'System Idle. Waiting for image upload...';
  statusMessage.className = 'text-[15px] font-medium text-textSecondary';
  statusLog.classList.add('hidden');

  inputDimX.value = '';
  inputDimY.value = '';
  inputDimZ.value = '';
  inputDimX.setAttribute('disabled', 'true');
  inputDimY.setAttribute('disabled', 'true');
  inputDimZ.setAttribute('disabled', 'true');
  
  statStudGrid.textContent = '-';
  statStudCount.textContent = '-';
};

// Handle file selection (shared logic for click & drag-drop)
async function handleFileSelected(filePath) {
  selectedImagePath = filePath;
  const fileName = filePath.split(/[\\/]/).pop();
  fileNameEl.textContent = fileName;
  filePathEl.textContent = filePath;
  filePathEl.className = 'text-[12px] text-primary font-mono mt-1 break-all px-2';

  try {
    // Show spinner in status panel while loading image preview
    statusSpinner.classList.remove('hidden');
    statusIcon.innerHTML = '';
    statusMessage.textContent = 'Loading image preview...';
    statusMessage.className = 'text-[15px] font-medium text-textMain';

    // Load preview thumbnail as base64 from Rust backend
    const fileUrl = await invoke('read_image_base64', { path: filePath });
    imagePreview.src = fileUrl;
    imagePreview.classList.remove('hidden');
    placeholderText.classList.add('hidden');

    // Pre-calculate physical and brick stats in real-time
    const img = new Image();
    img.src = fileUrl;
    img.onload = () => {
      let w = img.width;
      let h = img.height;

      // Apply landscape rotation rule
      if (h > w) {
        let temp = w;
        w = h;
        h = temp;
      }

      // Apply dynamic image resize division matching python logic
      let div = 2;
      if (w > 5000 || h > 5000) div = 8;
      else if (w >= 2000 || h >= 2000) div = 6;
      else if (w >= 1000 || h >= 1000) div = 5;
      else if (w >= 500 || h >= 500) div = 3;
      else div = 2;

      const resizedW = Math.max(1, Math.floor(w / div));
      const resizedH = Math.max(1, Math.floor(h / div));

      imageAspectRatio = resizedW / resizedH;
      currentHeight = 40.0;
      currentWidth = 40.0 * imageAspectRatio;
      currentThickness = 5.5;

      // Enable the inputs
      inputDimX.removeAttribute('disabled');
      inputDimY.removeAttribute('disabled');
      inputDimZ.removeAttribute('disabled');

      updateStatsAndFields();
    };

    // Enable convert button
    convertBtn.removeAttribute('disabled');
    statusSpinner.classList.add('hidden');
    statusIcon.innerHTML = `<i class="bi bi-info-circle-fill"></i>`;
    statusIcon.className = 'text-primary';
    statusMessage.textContent = 'Image loaded. Ready to generate STL model.';
    statusMessage.className = 'text-[15px] font-medium text-textMain';
  } catch (error) {
    console.error('Failed to load image preview:', error);
    statusSpinner.classList.add('hidden');
    statusIcon.innerHTML = `<i class="bi bi-exclamation-triangle-fill text-danger"></i>`;
    statusMessage.textContent = 'Failed to load image preview.';
    statusMessage.className = 'text-[15px] font-medium text-danger';
  }
}

// Select image file via file dialog
dropzone.addEventListener('click', async () => {
  try {
    const selected = await open({
      multiple: false,
      filters: [{
        name: 'Images',
        extensions: ['png', 'jpg', 'jpeg', 'bmp']
      }]
    });

    if (selected) {
      await handleFileSelected(selected);
    }
  } catch (error) {
    console.error('File dialog open error:', error);
  }
});

// HTML5 Drag and Drop Events
dropzone.addEventListener('dragover', (e) => {
  e.preventDefault();
  dropzone.classList.add('border-primary/50', 'bg-surface/80');
});

dropzone.addEventListener('dragleave', () => {
  dropzone.classList.remove('border-primary/50', 'bg-surface/80');
});

dropzone.addEventListener('drop', async (e) => {
  e.preventDefault();
  dropzone.classList.remove('border-primary/50', 'bg-surface/80');
  
  const files = e.dataTransfer.files;
  if (files && files.length > 0) {
    const file = files[0];
    const filePath = file.path || file.name;
    if (filePath) {
      const ext = filePath.split('.').pop().toLowerCase();
      if (['png', 'jpg', 'jpeg', 'bmp'].includes(ext)) {
        await handleFileSelected(filePath);
      }
    }
  }
});

// Tauri Native Window Drag and Drop Events
if (window.__TAURI__ && window.__TAURI__.event) {
  window.__TAURI__.event.listen('tauri://drag-drop', async (event) => {
    let filePath = null;
    if (Array.isArray(event.payload)) {
      filePath = event.payload[0];
    } else if (event.payload && Array.isArray(event.payload.paths)) {
      filePath = event.payload.paths[0];
    }
    
    if (filePath) {
      const ext = filePath.split('.').pop().toLowerCase();
      if (['png', 'jpg', 'jpeg', 'bmp'].includes(ext)) {
        await handleFileSelected(filePath);
      }
    }
  });

  window.__TAURI__.event.listen('tauri://drag-over', () => {
    dropzone.classList.add('border-primary/50', 'bg-surface/80');
  });

  window.__TAURI__.event.listen('tauri://drag-leave', () => {
    dropzone.classList.remove('border-primary/50', 'bg-surface/80');
  });
}

// Run generation
convertBtn.addEventListener('click', async () => {
  if (!selectedImagePath) return;

  try {
    const defaultName = selectedImagePath.split(/[\\/]/).pop().split('.').slice(0, -1).join('.') + '.stl';
    const savePath = await save({
      defaultPath: defaultName,
      filters: [{
        name: 'STL Model',
        extensions: ['stl']
      }]
    });

    if (!savePath) return; // User cancelled

    // Update status indicators
    statusSpinner.classList.remove('hidden');
    statusIcon.innerHTML = '';
    statusMessage.textContent = 'Generating STL 3D model (running Python engine)...';
    statusMessage.className = 'text-[15px] font-medium text-textMain';
    statusLog.classList.add('hidden');
    convertBtn.setAttribute('disabled', 'true');
    convertBtn.innerHTML = '<i class="bi bi-cpu animate-pulse"></i> Generating...';

    // Call Rust backend command
    const result = await invoke('convert_image', {
      imagePath: selectedImagePath,
      outputPath: savePath,
      mode: currentMode,
      studs: currentStuds,
      ring: currentRing,
      width: currentWidth,
      height: currentHeight,
      thickness: currentThickness
    });

    // Update state to success
    statusSpinner.classList.add('hidden');
    statusIcon.innerHTML = `<i class="bi bi-check-circle-fill text-success"></i>`;
    statusMessage.textContent = 'STL file generated successfully!';
    statusMessage.className = 'text-[15px] font-bold text-success';
    statusLog.classList.remove('hidden');
    statusLog.textContent = result;

    // Save to recent exports
    addRecentExport(savePath);

  } catch (error) {
    // Handle error
    statusSpinner.classList.add('hidden');
    statusIcon.innerHTML = `<i class="bi bi-exclamation-triangle-fill text-danger"></i>`;
    statusMessage.textContent = 'Mesh generation failed.';
    statusMessage.className = 'text-[15px] font-bold text-danger';
    statusLog.classList.remove('hidden');
    statusLog.textContent = String(error);
  } finally {
    convertBtn.removeAttribute('disabled');
    convertBtn.innerHTML = '<i class="bi bi-play-fill text-lg"></i> Generate STL';
  }
});

// Recent exports helper functions
function addRecentExport(filePath) {
  const exports = getRecentExports();
  const filename = filePath.split(/[\\/]/).pop();
  
  // Filter duplicates
  const filtered = exports.filter(item => item.path !== filePath);
  
  // Add new item at the top
  filtered.unshift({
    name: filename,
    path: filePath,
    timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) + ' ' + new Date().toLocaleDateString()
  });

  // Limit to last 5
  if (filtered.length > 5) {
    filtered.pop();
  }

  localStorage.setItem('recent_exports', JSON.stringify(filtered));
  updateRecentExportsUI();
}

function getRecentExports() {
  const stored = localStorage.getItem('recent_exports');
  return stored ? JSON.parse(stored) : [];
}

function updateRecentExportsUI() {
  const exports = getRecentExports();
  recentExportsList.innerHTML = '';

  if (exports.length === 0) {
    recentExportsList.innerHTML = `<div class="text-[13px] text-textSecondary italic text-center py-4">No recent exports found.</div>`;
    return;
  }

  exports.forEach(item => {
    const row = document.createElement('div');
    row.className = 'flex items-center justify-between p-2.5 hover:bg-surface rounded-lg border border-transparent hover:border-border transition-all';
    
    row.innerHTML = `
      <div class="flex flex-col text-left min-w-0 flex-1 pr-4">
        <span class="text-[14px] font-semibold text-textMain truncate">${item.name}</span>
        <span class="text-[11px] text-textSecondary font-mono truncate mt-0.5" title="${item.path}">${item.path}</span>
      </div>
      <div class="flex items-center gap-3 flex-shrink-0">
        <span class="text-[12px] text-textSecondary">${item.timestamp.split(' ')[0]}</span>
        <button class="w-8 h-8 rounded-md bg-surface hover:bg-card border border-border flex items-center justify-center text-textSecondary hover:text-primary transition-colors" title="Locate File">
          <i class="bi bi-folder2-open"></i>
        </button>
      </div>
    `;

    // Hook up opener reveal action
    row.querySelector('button').addEventListener('click', async () => {
      try {
        await openPath(item.path);
      } catch (err) {
        console.error('Failed to open file path:', err);
      }
    });

    recentExportsList.appendChild(row);
  });
}
