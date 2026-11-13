const noteForm = document.getElementById('note-form');
const noteIdInput = document.getElementById('note-id');
const titleInput = document.getElementById('title');
const bodyInput = document.getElementById('body');
const tagsInput = document.getElementById('tags');
const searchInput = document.getElementById('search');
const tagFilterInput = document.getElementById('tag-filter');
const limitSelect = document.getElementById('limit-select');
const listContainer = document.getElementById('notes-list');
const statusBox = document.getElementById('status');
const formTitle = document.getElementById('form-title');
const resetButton = document.getElementById('reset-form');

function setStatus(message, isError = false) {
  statusBox.textContent = message;
  statusBox.style.color = isError ? '#b91c1c' : '#475569';
}

async function fetchNotes() {
  const params = new URLSearchParams();
  const query = searchInput.value.trim();
  const tagFilter = tagFilterInput.value.trim();
  const limit = limitSelect.value;

  if (query) params.set('q', query);
  if (tagFilter) params.set('tag', tagFilter);
  params.set('limit', limit);

  try {
    const response = await fetch(`/notes?${params.toString()}`);
    if (!response.ok) {
      throw new Error('Unable to load notes');
    }
    const payload = await response.json();
    renderNotes(payload.items || []);
    setStatus(`Showing ${payload.items.length} of ${payload.total} notes`);
  } catch (error) {
    setStatus(error.message, true);
  }
}

function renderNotes(notes) {
  if (!notes.length) {
    listContainer.innerHTML = '<div class="empty-state">No notes match your current filters.</div>';
    return;
  }

  listContainer.innerHTML = notes
    .map(
      (note) => `
        <article class="note-card" data-id="${note.id}">
          <h3>${escapeHtml(note.title)}</h3>
          <p>${escapeHtml(note.body)}</p>
          <div class="tags">
            ${(note.tags || []).map((tag) => `<span class="tag">${escapeHtml(tag)}</span>`).join('')}
          </div>
          <div class="note-actions">
            <button type="button" class="secondary edit-button" data-id="${note.id}">Edit</button>
            <button type="button" class="danger delete-button" data-id="${note.id}">Delete</button>
          </div>
        </article>
      `,
    )
    .join('');

  listContainer.querySelectorAll('.edit-button').forEach((button) => {
    button.addEventListener('click', async () => {
      const noteId = Number(button.dataset.id);
      const response = await fetch(`/notes/${noteId}`);
      const note = await response.json();
      noteIdInput.value = String(note.id);
      titleInput.value = note.title;
      bodyInput.value = note.body;
      tagsInput.value = (note.tags || []).join(', ');
      formTitle.textContent = 'Edit note';
      titleInput.focus();
    });
  });

  listContainer.querySelectorAll('.delete-button').forEach((button) => {
    button.addEventListener('click', async () => {
      const noteId = Number(button.dataset.id);
      const response = await fetch(`/notes/${noteId}`, { method: 'DELETE' });
      if (!response.ok) {
        setStatus('Unable to delete note.', true);
        return;
      }
      setStatus('Note deleted.');
      resetForm();
      await fetchNotes();
    });
  });
}

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

function resetForm() {
  noteForm.reset();
  noteIdInput.value = '';
  formTitle.textContent = 'Create note';
}

noteForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  const noteId = noteIdInput.value;
  const payload = {
    title: titleInput.value.trim(),
    body: bodyInput.value.trim(),
    tags: tagsInput.value
      .split(',')
      .map((value) => value.trim())
      .filter(Boolean),
  };

  if (!payload.title || !payload.body) {
    setStatus('Title and body are required.', true);
    return;
  }

  const url = noteId ? `/notes/${noteId}` : '/notes';
  const method = noteId ? 'PUT' : 'POST';

  try {
    const response = await fetch(url, {
      method,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });

    const result = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(result.detail || 'Request failed');
    }

    setStatus(noteId ? 'Note updated.' : 'Note created.');
    resetForm();
    await fetchNotes();
  } catch (error) {
    setStatus(error.message, true);
  }
});

searchInput.addEventListener('input', fetchNotes);
tagFilterInput.addEventListener('input', fetchNotes);
limitSelect.addEventListener('change', fetchNotes);
resetButton.addEventListener('click', () => {
  resetForm();
  setStatus('Form cleared.');
});

resetForm();
fetchNotes();
