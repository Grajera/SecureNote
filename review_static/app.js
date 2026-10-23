'use strict';
const byId = (id) => document.getElementById(id);
const audio = byId('audio');
let trashMode = false;
let csrf = '', recordings = [], current = null, activeRow = -1, previewFor = '', pendingSeek = null;
let searchTerm = '', editAction = null, saving = false, selecting = 0, previewRequested = new Set();
let recorder = null, microphone = null, captureChunks = [], cancelCapture = false, captureTimer = null;
function element(tag, className, text) {
  const result = document.createElement(tag);
  if (className) result.className = className;
  if (text !== undefined) result.textContent = text;
  return result;
}
function clock(seconds) {
  const total = Math.max(0, Math.floor(Number(seconds) || 0));
  return (total >= 3600 ? String(Math.floor(total / 3600)).padStart(2, '0') + ':' : '') +
    String(Math.floor(total / 60) % 60).padStart(2, '0') + ':' + String(total % 60).padStart(2, '0');
}
function notify(text) { byId('message').textContent = text; byId('message').hidden = !text; }
async function api(path, method = 'GET', data) {
  const headers = {};
  if (method !== 'GET') headers['X-Review-CSRF'] = csrf;
  if (data !== undefined) headers['Content-Type'] = 'application/json';
  const response = await fetch(path, {method, headers, body: data === undefined ? undefined : JSON.stringify(data)});
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || 'Request failed');
  return result;
}
function run(action) { return Promise.resolve().then(action).catch(error => notify(error.message)); }
function jobPath(suffix = '') { return '/api/jobs/' + current.id + suffix; }
function stamp(seconds, play = true) {
  const button = element('button', 'timestamp', clock(seconds));
  button.type = 'button';
  button.setAttribute('aria-label', 'Listen from ' + clock(seconds));
  button.onclick = () => seekTo(seconds, play, true);
  return button;
}
function highlightRow(seconds, scroll = false) {
  if (!current || !current.segments.length) return;
  let low = 0, high = current.segments.length - 1, index = 0;
  while (low <= high) {
    const middle = Math.floor((low + high) / 2);
    if (current.segments[middle].start <= seconds + 0.03) { index = middle; low = middle + 1; }
    else high = middle - 1;
  }
  if (activeRow !== index) {
    if (activeRow >= 0) byId('segment-' + activeRow)?.classList.remove('active');
    activeRow = index;
    byId('segment-' + index)?.classList.add('active');
    if (byId('followPlayback').checked && !audio.paused) scroll = true;
  }
  const row = byId('segment-' + index);
  if (scroll && row) {
    // Scroll only the transcript container; never pull the whole page away.
    const container = byId('transcript');
    container.scrollTop = Math.max(0, row.offsetTop - container.offsetTop - container.clientHeight / 3);
  }
}
function seekTo(seconds, play = false, scroll = false) {
  if (!current) return;
  const value = Math.max(0, Math.min(seconds, current.duration || seconds));
  pendingSeek = {seconds: value, play};
  if (audio.readyState >= 1 && previewFor === current.id) {
    audio.currentTime = value; pendingSeek = null;
    if (play) audio.play().catch(() => notify('Press Play to start the recording at this timestamp.'));
  } else if (play) {
    notify('Audio is preparing. The selected timestamp will be ready when playback loads.');
  }
  byId('seek').value = value;
  byId('currentTime').textContent = clock(value);
  highlightRow(value, scroll);
}
function updatePlayback() {
  byId('currentTime').textContent = clock(audio.currentTime);
  byId('seek').value = audio.currentTime || 0;
  highlightRow(audio.currentTime);
}
audio.addEventListener('timeupdate', updatePlayback);
audio.addEventListener('play', () => { byId('playButton').textContent = 'Ⅱ'; byId('playButton').setAttribute('aria-label', 'Pause recording'); });
audio.addEventListener('pause', () => {
  byId('playButton').textContent = '▶'; byId('playButton').setAttribute('aria-label', 'Play recording');
  if (current && previewFor === current.id) localStorage.setItem('securenote-position-' + current.id, String(audio.currentTime));
});
audio.addEventListener('loadedmetadata', () => {
  audio.playbackRate = Number(byId('speed').value);
  if (current && !current.duration && Number.isFinite(audio.duration)) {
    current.duration = audio.duration;
    byId('seek').max = audio.duration; byId('totalTime').textContent = clock(audio.duration);
  }
  byId('playbackStatus').textContent = 'Ready to listen';
  if (pendingSeek) { const pending = pendingSeek; seekTo(pending.seconds, pending.play, true); }
});
audio.addEventListener('error', () => { if (audio.getAttribute('src')) byId('playbackStatus').textContent = 'Playback unavailable. Check FFmpeg and try reopening the recording.'; });
function markedText(text, query) {
  const fragment = document.createDocumentFragment();
  const words = query.toLowerCase().trim().split(/\s+/).filter(Boolean);
  if (!words.length) { fragment.append(document.createTextNode(text)); return fragment; }
  // Index literal matches without constructing a regular expression from input.
  const lower = text.toLowerCase(); let offset = 0;
  while (offset < text.length) {
    let next = -1, length = 0;
    for (const word of words) {
      const index = lower.indexOf(word, offset);
      if (index >= 0 && (next < 0 || index < next)) { next = index; length = word.length; }
    }
    if (next < 0) { fragment.append(document.createTextNode(text.slice(offset))); break; }
    fragment.append(document.createTextNode(text.slice(offset, next)));
    fragment.append(element('mark', '', text.slice(next, next + length)));
    offset = next + length;
  }
  return fragment;
}
function renderTranscript() {
  const container = byId('transcript'); const position = container.scrollTop;
  const fragment = document.createDocumentFragment();
  current.segments.forEach((segment, index) => {
    const row = element('div', 'transcript-row' + (index === activeRow ? ' active' : ''));
    row.id = 'segment-' + index;
    row.append(stamp(segment.start));
    const text = element('p'); text.append(markedText(segment.text, searchTerm)); row.append(text);
    fragment.append(row);
  });
  if (!current.segments.length) fragment.append(element('p', 'empty-small', current.status === 'completed' ?
    'No speech was transcribed. Your recording is still available to listen to.' : 'The complete transcript will appear here when processing finishes.'));
  container.replaceChildren(fragment); container.scrollTop = position;
  byId('segmentCount').textContent = current.segments.length;
}
async function saveReview(changes) {
  if (!current || saving) throw new Error('A review save is still in progress. Try again in a moment.');
  saving = true; byId('saveStatus').textContent = 'Saving…';
  const identifier = current.id;
  try {
    const updated = await api('/api/jobs/' + identifier + '/review', 'POST', {version: current.annotation.version, ...changes});
    if (current?.id === identifier) current.annotation = updated;
    byId('saveStatus').textContent = 'Saved locally';
    return updated;
  } catch (error) { byId('saveStatus').textContent = 'Not saved'; throw error; }
  finally { saving = false; }
}
function renderNotes() {
  const container = byId('notes'); container.replaceChildren();
  const filter = byId('noteFilter').value.toLowerCase();
  const visible = current.notes.filter(note => (!note.hidden || byId('showHidden').checked) && filter.split(/\s+/).filter(Boolean).every(word => note.text.toLowerCase().includes(word)));
  byId('noteCount').textContent = current.notes.filter(note => !note.hidden).length;
  for (const category of ['Decisions', 'Action items', 'Key points', 'Follow-ups']) {
    const group = visible.filter(note => note.category === category);
    if (!group.length) continue;
    container.append(element('h3', 'note-category', category.toUpperCase()));
    for (const note of group) {
      const card = element('article', 'note-card' + (note.hidden ? ' hidden-note' : ''));
      card.dataset.noteId = note.id; card.append(element('p', '', note.text));
      const footer = element('div', 'note-footer'); const source = element('div');
      source.append(stamp(note.start));
      if (note.edited) source.append(element('span', 'edited-badge', 'Edited'));
      footer.append(source);
      const actions = element('div', 'note-actions');
      const edit = element('button', '', 'Edit');
      edit.onclick = () => openEditor('Edit note', note.text, 'Source: ' + note.source_text, async text => {
        await saveReview({edits: {...current.annotation.edits, [note.id]: text}});
        note.text = text; note.edited = true; renderNotes();
      });
      const hide = element('button', '', note.hidden ? 'Restore' : 'Hide');
      hide.onclick = () => run(async () => {
        const hidden = current.annotation.hidden.filter(id => id !== note.id);
        if (!note.hidden) hidden.push(note.id);
        await saveReview({hidden}); note.hidden = !note.hidden; renderNotes();
      });
      actions.append(edit, hide);
      if (note.edited) {
        const reset = element('button', '', 'Reset');
        reset.onclick = () => run(async () => {
          const edits = {...current.annotation.edits}; delete edits[note.id];
          await saveReview({edits}); note.text = note.source_text; note.edited = false; renderNotes();
        });
        actions.append(reset);
      }
      footer.append(actions); card.append(footer); container.append(card);
    }
  }
  if (!visible.length) container.append(element('p', 'empty-small', 'No automatic highlights to show. The full transcript stays available. Add your own note at any timestamp.'));
  renderBookmarks();
}
function renderBookmarks() {
  const container = byId('bookmarks'); container.replaceChildren();
  const bookmarks = current.annotation.bookmarks.filter(note => byId('noteFilter').value.toLowerCase().split(/\s+/).filter(Boolean).every(word => note.text.toLowerCase().includes(word))).sort((a, b) => a.start - b.start);
  for (const bookmark of bookmarks) {
    const card = element('article', 'note-card'); card.append(element('p', '', bookmark.text));
    const footer = element('div', 'note-footer'); footer.append(stamp(bookmark.start));
    const actions = element('div', 'note-actions');
    const edit = element('button', '', 'Edit');
    edit.onclick = () => openEditor('Edit bookmark', bookmark.text, 'Linked to ' + clock(bookmark.start), async text => {
      await saveReview({bookmarks: current.annotation.bookmarks.map(item => item.id === bookmark.id ? {...item, text} : item)}); renderBookmarks();
    });
    const remove = element('button', '', 'Remove');
    remove.onclick = () => run(async () => { await saveReview({bookmarks: current.annotation.bookmarks.filter(item => item.id !== bookmark.id)}); renderBookmarks(); });
    actions.append(edit, remove); footer.append(actions); card.append(footer); container.append(card);
  }
  if (!bookmarks.length) container.append(element('p', 'empty-small', 'Something worth keeping? Bookmark the current moment or add a personal note.'));
}
function openEditor(title, value, source, action) {
  editAction = action; byId('editorTitle').textContent = title; byId('editText').value = value;
  byId('editText').maxLength = title.toLowerCase().includes('bookmark') ? 1000 : 5000;
  byId('editSource').textContent = source; byId('editor').showModal(); byId('editText').focus();
}
byId('editForm').onsubmit = event => {
  event.preventDefault(); const text = byId('editText').value.trim(); if (!text) return;
  run(async () => { await editAction(text); byId('editor').close(); });
};
byId('cancelEdit').onclick = () => byId('editor').close();
function addBookmark() {
  if (!current || !current.duration) return;
  const start = Math.min(audio.currentTime || Number(byId('seek').value) || 0, current.duration);
  openEditor('Add bookmark', '', 'Save a personal note at ' + clock(start), async text => {
    await saveReview({bookmarks: [...current.annotation.bookmarks, {id: crypto.randomUUID().replaceAll('-', ''), start, text}]}); renderBookmarks();
  });
  byId('editText').maxLength = 1000;
}
function renderLibrary() {
  const filter = byId('librarySearch').value.toLowerCase(); const container = byId('library');
  container.replaceChildren(); byId('libraryCount').textContent = recordings.length;
  for (const recording of recordings.filter(item => item.title.toLowerCase().includes(filter))) {
    const button = element('button', 'library-item' + (current?.id === recording.id ? ' selected' : ''));
    button.dataset.recordingId = recording.id;
    button.append(element('strong', '', recording.title));
    const meta = element('small'); meta.append(element('span', '', new Date(recording.created_at).toLocaleDateString()),
      element('span', '', recording.reviewed ? '✓ Reviewed' : recording.status === 'completed' ? 'Ready to review' : recording.status));
    button.append(meta); button.onclick = () => run(() => selectRecording(recording.id)); container.append(button);
  }
}
async function refreshLibrary() { recordings = await api('/api/jobs' + (trashMode ? '?trash=1' : '')); renderLibrary(); }
function showJobStatus() {
  const failed = current.status === 'failed'; const busy = ['queued', 'processing'].includes(current.status);
  byId('jobStatus').hidden = !busy && !failed;
  byId('jobStatusTitle').textContent = failed ? 'Processing needs attention' : current.status === 'queued' ? 'Recording received · queued' : 'Transcribing on this computer…';
  byId('jobStatusText').textContent = failed ? current.error || 'Processing failed. Run securenote.py doctor for dependency checks.' : 'Your recording is stored locally. You can listen while the transcript and notes are prepared.';
  byId('retryButton').hidden = !failed;
}
async function ensurePreview() {
  if (!current) return;
  const identifier = current.id;
  if (current.preview === 'ready') {
    byId('playbackStatus').textContent = 'Ready to listen';
    if (previewFor !== identifier) {
      previewFor = identifier; audio.src = jobPath('/media'); audio.load();
    }
  } else if (current.preview === 'failed') {
    byId('playbackStatus').textContent = 'Playback preview failed. Check FFmpeg and reopen the recording.';
  } else {
    byId('playbackStatus').textContent = 'Preparing seekable audio…';
    if (!previewRequested.has(identifier)) {
      previewRequested.add(identifier); await api(jobPath('/prepare'), 'POST');
    }
  }
}
function renderDetail() {
  byId('deleteRecording').hidden = trashMode;
  byId('restoreRecording').hidden = !trashMode;
  byId('purgeRecording').hidden = !trashMode;
  byId('emptyState').hidden = true; byId('workspace').hidden = false;
  if (document.activeElement !== byId('recordingTitle')) byId('recordingTitle').value = current.title;
  byId('recordingMeta').textContent = (current.created_at ? new Date(current.created_at).toLocaleString() + '  ·  ' : '') + clock(current.duration) + '  ·  ' + current.device;
  byId('reviewButton').textContent = current.annotation.reviewed ? '✓ Reviewed' : 'Mark reviewed';
  byId('reviewButton').setAttribute('aria-pressed', String(current.annotation.reviewed));
  byId('seek').max = current.duration || 1; byId('totalTime').textContent = clock(current.duration);
  showJobStatus(); renderNotes(); renderTranscript();
}
async function selectRecording(identifier) {
  if (saving) { notify('Wait for the current note to finish saving.'); return; }
  const request = ++selecting;
  audio.pause(); audio.removeAttribute('src'); audio.load(); previewFor = ''; pendingSeek = null; activeRow = -1;
  clearSearch(); notify('');
  const detail = await api('/api/jobs/' + identifier);
  if (request !== selecting) return;
  current = detail;
  byId('answerResult').replaceChildren(); byId('answerResult').hidden = true;
  byId('askQuestion').value = '';
  byId('quickNote').value = sessionStorage.getItem('draft-' + identifier) || '';
  byId('noteFilter').value = ''; 
  pendingSeek = {seconds: Number(localStorage.getItem('securenote-position-' + identifier)) || 0, play: false};
  byId('seek').value = pendingSeek.seconds;
  renderDetail(); renderLibrary(); await ensurePreview();
}
function clearSearch() {
  searchTerm = ''; byId('transcriptSearch').value = ''; byId('searchResults').replaceChildren();
  byId('searchResults').hidden = true; byId('clearSearch').hidden = true; byId('searchCount').textContent = 'Complete transcript';
  if (current) renderTranscript();
}
byId('searchForm').onsubmit = event => {
  event.preventDefault();
  run(async () => {
    if (!current) return;
    const identifier = current.id, query = byId('transcriptSearch').value.trim();
    if (!query) { clearSearch(); return; }
    const matches = await api(jobPath('/search?q=') + encodeURIComponent(query));
    if (current.id !== identifier) return;
    searchTerm = query; renderTranscript(); byId('searchResults').replaceChildren();
    byId('searchResults').hidden = false; byId('clearSearch').hidden = false;
    byId('searchCount').textContent = matches.length + (matches.length === 1 ? ' match' : ' matches');
    for (const match of matches) {
      const button = element('button', 'search-hit'); button.append(element('span', 'timestamp', clock(match.start)));
      button.append(element('div', '', match.text));
      const index = current.segments.findIndex(segment => segment.end >= match.start);
      const neighbors = current.segments.slice(Math.max(0, index - 1), index + 2).map(segment => segment.text).join(' ');
      button.append(element('small', '', 'Context: ' + neighbors));
      button.onclick = () => seekTo(match.start, true, true);
      byId('searchResults').append(button);
    }
    if (!matches.length) byId('searchResults').append(element('p', 'empty-small', 'No matching passages. Try words used in the recording; the full transcript remains below.'));
  });
};
byId('clearSearch').onclick = clearSearch;
byId('librarySearch').oninput = renderLibrary;
byId('showHidden').onchange = renderNotes;
byId('playButton').onclick = () => { if (audio.readyState < 1) return notify('Audio is still preparing.'); audio.paused ? audio.play().catch(error => notify(error.message)) : audio.pause(); };
byId('backButton').onclick = () => seekTo((audio.currentTime || 0) - 10, false, true);
byId('forwardButton').onclick = () => seekTo((audio.currentTime || 0) + 10, false, true);
byId('seek').oninput = event => seekTo(Number(event.target.value), false, true);
byId('speed').onchange = () => { audio.playbackRate = Number(byId('speed').value); localStorage.setItem('securenote-speed', byId('speed').value); };
byId('bookmarkButton').onclick = addBookmark; byId('addNote').onclick = () => byId('quickNote').focus();
byId('recordingTitle').onchange = () => run(async () => {
  const title = byId('recordingTitle').value.trim() || 'Untitled recording';
  await saveReview({title}); current.title = title; await refreshLibrary();
});
byId('reviewButton').onclick = () => run(async () => { await saveReview({reviewed: !current.annotation.reviewed}); renderDetail(); await refreshLibrary(); });
byId('exportNotes').onclick = () => { if (current) window.location.href = jobPath('/export'); };
byId('exportTranscript').onclick = () => { if (current) window.location.href = jobPath('/export?format=transcript'); };
byId('retryButton').onclick = () => run(async () => { const result = await api(jobPath('/retry'), 'POST'); await refreshLibrary(); await selectRecording(result.id); });
async function importRecording(file, name) {
  notify(''); byId('uploadStatus').hidden = false; byId('importButton').disabled = true;
  byId('uploadLabel').textContent = 'Importing ' + name + ' into the local recorder queue…'; byId('uploadProgress').value = 0;
  try {
    const result = await new Promise((resolve, reject) => {
      const request = new XMLHttpRequest(); request.open('POST', '/api/import');
      request.setRequestHeader('X-Review-CSRF', csrf);
      request.setRequestHeader('X-Recording-Title', encodeURIComponent(name.replace(/\.[a-z0-9]+$/i, '')));
      request.upload.onprogress = event => { if (event.lengthComputable) byId('uploadProgress').value = event.loaded / event.total * 100; };
      request.onload = () => {
        try { const response = JSON.parse(request.responseText); request.status < 300 ? resolve(response) : reject(new Error(response.error)); }
        catch { reject(new Error('The local import did not return a valid response.')); }
      };
      request.onerror = () => reject(new Error('The local workspace connection was interrupted.'));
      request.send(file);
    });
    await refreshLibrary(); await selectRecording(result.id);
  } finally { byId('uploadStatus').hidden = true; byId('importButton').disabled = false; }
}
byId('fileInput').onchange = () => { const file = byId('fileInput').files[0]; if (file) run(() => importRecording(file, file.name)); byId('fileInput').value = ''; };
byId('importButton').onclick = () => byId('fileInput').click(); byId('emptyImport').onclick = () => byId('fileInput').click();
function loadSample() { run(async () => { notify('Preparing your local sample meeting…'); const result = await api('/api/example', 'POST'); await refreshLibrary(); await selectRecording(result.id); }); }
byId('sampleButton').onclick = loadSample; byId('emptySample').onclick = loadSample;
byId('recordButton').onclick = () => run(async () => {
  if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) throw new Error('Microphone recording is unavailable in this browser. Import a recording instead.');
  microphone = await navigator.mediaDevices.getUserMedia({audio: true});
  cancelCapture = false; captureChunks = [];
  try { recorder = new MediaRecorder(microphone); }
  catch (error) { microphone.getTracks().forEach(track => track.stop()); throw error; }
  recorder.onerror = () => { cancelCapture = true; microphone.getTracks().forEach(track => track.stop()); byId('recordButton').disabled = false; byId('captureControls').hidden = true; clearInterval(captureTimer); notify('Microphone capture failed. Import a recording or try again.'); };
  const started = Date.now();
  recorder.ondataavailable = event => { if (event.data.size) captureChunks.push(event.data); };
  recorder.onstop = () => {
    clearInterval(captureTimer); microphone.getTracks().forEach(track => track.stop());
    byId('captureControls').hidden = true; byId('recordButton').disabled = false;
    if (!cancelCapture) {
      const type = recorder.mimeType || 'audio/webm';
      const blob = new Blob(captureChunks, {type});
      run(() => importRecording(blob, 'Recording ' + new Date().toLocaleString()));
    }
  };
  recorder.start(1000); byId('captureControls').hidden = false; byId('recordButton').disabled = true;
  byId('captureTime').textContent = '● Recording 00:00';
  captureTimer = setInterval(() => {
    byId('captureTime').textContent = '● Recording ' + clock((Date.now() - started) / 1000);
    if (Date.now() - started > 2 * 60 * 60 * 1000) recorder.stop();
  }, 1000);
});
byId('stopRecording').onclick = () => { if (recorder?.state === 'recording') recorder.stop(); };
byId('cancelRecording').onclick = () => { cancelCapture = true; if (recorder?.state === 'recording') recorder.stop(); };
window.addEventListener('beforeunload', event => { if (recorder?.state === 'recording' || saving) { event.preventDefault(); event.returnValue = ''; } });
document.addEventListener('keydown', event => {
  if (event.ctrlKey || event.altKey || event.metaKey || byId('editor').open || ['INPUT', 'TEXTAREA', 'SELECT', 'BUTTON'].includes(event.target.tagName)) return;
  if (event.key === '/') { event.preventDefault(); byId('transcriptSearch').focus(); }
  else if (event.key === ' ') { event.preventDefault(); byId('playButton').click(); }
  else if (event.key === 'ArrowLeft') { event.preventDefault(); seekTo((audio.currentTime || 0) - 5, false, true); }
  else if (event.key === 'ArrowRight') { event.preventDefault(); seekTo((audio.currentTime || 0) + 5, false, true); }
});
async function start() {
  try {
    const key = new URLSearchParams(location.hash.slice(1)).get('session');
    if (key) {
      const response = await fetch('/api/session', {method: 'POST', headers: {'X-Session-Key': key}});
      const result = await response.json(); if (!response.ok) throw new Error(result.error); csrf = result.csrf;
      history.replaceState(null, '', '/');
    } else csrf = (await api('/api/session')).csrf;
    const savedSpeed = localStorage.getItem('securenote-speed');
    if (['0.75', '1', '1.25', '1.5', '2'].includes(savedSpeed)) byId('speed').value = savedSpeed;
    const engine = await api('/api/engine');
    document.querySelector('.privacy-badge').textContent = '● ' + engine.device.toUpperCase() + ' · ' + engine.compute_type + ' · Local AI';
    await refreshLibrary();
    if (recordings.length) await selectRecording(recordings[0].id);
    setInterval(() => run(async () => {
      if (saving) return;
      await refreshLibrary();
      if (current && (['queued', 'processing'].includes(current.status) || current.preview === 'preparing' || current.preview === 'not_prepared')) {
        const identifier = current.id, fresh = await api(jobPath());
        if (current.id !== identifier || saving) return;
        const completed = fresh.status !== current.status;
        current.preview = fresh.preview;
        if (fresh.duration > 0 && current.duration !== fresh.duration) {
          current.duration = fresh.duration; byId('seek').max = fresh.duration; byId('totalTime').textContent = clock(fresh.duration);
        }
        if (completed) { current = fresh; renderDetail(); }
        await ensurePreview();
      }
    }), 1800);
  } catch (error) { notify(error.message); }
}
start();

byId('noteFilter').oninput = () => { if (current) renderNotes(); };
byId('quickNote').oninput = () => { if (current) sessionStorage.setItem('draft-' + current.id, byId('quickNote').value); };
byId('quickNote').onkeydown = event => { if (event.ctrlKey && event.key === 'Enter') { event.preventDefault(); byId('quickNoteForm').requestSubmit(); } };
byId('quickNoteForm').onsubmit = event => {
  event.preventDefault();
  run(async () => {
    if (!current) return;
    const text = byId('quickNote').value.trim(); if (!text) return;
    const id = current.id;
    await saveReview({bookmarks: [...current.annotation.bookmarks, {id: crypto.randomUUID().replaceAll('-', ''), start: Math.min(audio.currentTime || 0, current.duration || 0), text}]});
    sessionStorage.removeItem('draft-' + id); byId('quickNote').value = ''; renderBookmarks();
  });
};
async function resetSelection() {
  audio.pause(); current = null; audio.removeAttribute('src'); audio.load();
  byId('workspace').hidden = true; byId('emptyState').hidden = false;
  await refreshLibrary(); if (recordings.length) await selectRecording(recordings[0].id);
}
byId('trashView').onclick = () => run(async () => {
  trashMode = !trashMode; byId('trashView').textContent = trashMode ? '← Back to recordings' : 'Open Trash';
  await resetSelection();
});
byId('deleteRecording').onclick = () => run(async () => {
  if (!current || !confirm('Move this recording and its notes to Trash? You can restore it later.')) return;
  await api(jobPath('/trash'), 'POST'); await resetSelection(); notify('Moved to Trash. Open Trash to restore or permanently delete.');
});
byId('restoreRecording').onclick = () => run(async () => { await api(jobPath('/restore'), 'POST'); await resetSelection(); notify('Recording restored.'); });
byId('purgeRecording').onclick = () => run(async () => {
  if (!current || !confirm('Permanently delete the managed recording, transcript, results and personal notes? This cannot be undone. Original imported files, separate recorder spools and backups are not removed.')) return;
  await api(jobPath('/purge'), 'POST'); await resetSelection(); notify('Managed recording files deleted.');
});
byId('closeGlobalSearch').onclick = () => { byId('globalResults').hidden = true; byId('globalQuery').value = ''; };
byId('globalSearchForm').onsubmit = event => {
  event.preventDefault(); run(async () => {
    const query = byId('globalQuery').value.trim();
    const results = await api('/api/search?q=' + encodeURIComponent(query));
    const box = byId('globalResults'); box.hidden = false; box.replaceChildren(element('h3', '', results.length + ' results · notes first (up to 100)'));
    for (const hit of results) {
      const button = element('button', 'search-hit');
      button.append(element('small', '', hit.title + ' · ' + hit.kind + ' · ' + clock(hit.start)));
      const text = element('p'); text.append(markedText(hit.text, query)); button.append(text);
      button.onclick = () => run(async () => {
        trashMode = false; byId('trashView').textContent = 'Open Trash'; await refreshLibrary();
        await selectRecording(hit.id); seekTo(hit.start, false, true);
        if (hit.kind !== 'Transcript') { byId('noteFilter').value = query; renderNotes(); }
        box.hidden = true;
      }); box.append(button);
    }
    if (!results.length) box.append(element('p', '', 'No matching notes or transcript passages. Try a word from the recording. Trash is excluded.'));
  });
};

byId('askForm').onsubmit = event => {
  event.preventDefault(); run(async () => {
    if (!current) return;
    const identifier = current.id;
    const question = byId('askQuestion').value.trim();
    if (!question) return;
    byId('askButton').disabled = true;
    const box = byId('answerResult'); box.hidden = false;
    box.replaceChildren(element('p', '', 'Finding evidence and generating an answer locally…'));
    try {
      const result = await api('/api/jobs/' + identifier + '/ask', 'POST', {question});
      if (current?.id !== identifier) return;
      box.replaceChildren(element('p', 'rag-answer', result.answer));
      box.append(element('small', '', 'Status: ' + result.status.replaceAll('_', ' ') + ' · ' + (result.latency_ms / 1000).toFixed(2) + ' seconds'));
      if (result.retrieved.length) box.append(element('h3', '', 'Retrieved transcript evidence'));
      for (const source of result.retrieved) {
        const evidence = element('article', 'rag-evidence');
        evidence.append(stamp(source.start));
        evidence.append(element('p', '', source.text)); box.append(evidence);
      }
      if (result.status === 'answered') {
        const keep = element('button', 'quiet', 'Save answer to my notes');
        keep.onclick = () => run(async () => {
          if (current?.id !== identifier) return;
          await saveReview({bookmarks: [...current.annotation.bookmarks, {
            id: crypto.randomUUID().replaceAll('-', ''), start: Math.min(result.sources[0].start, current.duration),
            text: ('Q: ' + question + '\nAnswer: ' + result.answer).slice(0, 1000)}]});
          keep.disabled = true; keep.textContent = 'Saved to your notes'; renderBookmarks();
        }); box.append(keep);
      }
    } catch (error) {
      if (current?.id === identifier) box.replaceChildren(element('p', '', error.message));
    } finally { byId('askButton').disabled = false; }
  });
};
