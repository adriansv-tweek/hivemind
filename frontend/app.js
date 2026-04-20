const API_BASE_URL = "http://127.0.0.1:8000";

const noteInput = document.getElementById("noteInput");
const pickFileBtn = document.getElementById("pickFileBtn");
const fileInput = document.getElementById("fileInput");
const uploadFileBtn = document.getElementById("uploadFileBtn");
const uploadStatus = document.getElementById("uploadStatus");
const uploadProgress = document.getElementById("uploadProgress");
const uploadProgressText = document.getElementById("uploadProgressText");
const toggleSearchBtn = document.getElementById("toggleSearchBtn");
const searchPanel = document.getElementById("searchPanel");
const appShell = document.querySelector(".app-shell");
const searchInput = document.getElementById("searchInput");
const loadRecentBtn = document.getElementById("loadRecentBtn");
const notesList = document.getElementById("notesList");
const statusText = document.getElementById("statusText");
const notesMeta = document.getElementById("notesMeta");
const REQUEST_TIMEOUT_MS = 20000;
const FILE_UPLOAD_TIMEOUT_MS = 120000;
let pendingPastedFile = null;
const SEARCH_ICON_SVG = `
  <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true" focusable="false">
    <circle cx="11" cy="11" r="6.5" fill="none" stroke="currentColor" stroke-width="1.8"></circle>
    <line x1="16" y1="16" x2="21" y2="21" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"></line>
  </svg>
`;
const CLOSE_ICON_SVG = `
  <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true" focusable="false">
    <line x1="6" y1="6" x2="18" y2="18" stroke="currentColor" stroke-width="1.9" stroke-linecap="round"></line>
    <line x1="18" y1="6" x2="6" y2="18" stroke="currentColor" stroke-width="1.9" stroke-linecap="round"></line>
  </svg>
`;

function setStatus(message, isError = false) {
  statusText.textContent = message;
  statusText.classList.toggle("error", isError);
}

function formatTags(tags) {
  if (!tags || tags.length === 0) {
    return "No tags";
  }
  return tags.join(", ");
}

async function fetchWithTimeout(url, options = {}, timeoutMs = REQUEST_TIMEOUT_MS) {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(url, { ...options, signal: controller.signal });
  } finally {
    clearTimeout(timeoutId);
  }
}

function getErrorMessage(error, fallbackMessage) {
  if (error?.name === "AbortError") {
    return "Request timed out. Check if backend is running.";
  }
  if (error?.message) {
    return error.message;
  }
  return fallbackMessage;
}

function setUploadStatus(message, isError = false) {
  uploadStatus.textContent = message;
  uploadStatus.classList.toggle("error", isError);
}

function setUploadInProgress(isLoading, message = "Processing file...") {
  uploadProgress.classList.toggle("visible", isLoading);
  uploadProgressText.textContent = message;
  uploadFileBtn.disabled = isLoading;
  pickFileBtn.disabled = isLoading;
}

function autoResizeNoteInput() {
  // Grow naturally with content while keeping a sensible max height.
  noteInput.style.height = "auto";
  const nextHeight = Math.min(noteInput.scrollHeight, 260);
  noteInput.style.height = `${Math.max(nextHeight, 56)}px`;
}

function setPendingPastedFile(file) {
  pendingPastedFile = file;
  if (!file) {
    setUploadStatus("");
    uploadFileBtn.style.display = "none";
    return;
  }
  uploadFileBtn.style.display = "inline-block";
  setUploadStatus(`Attached file ready: ${file.name}`);
}

function clearRenderedNotes() {
  notesMeta.textContent = "";
  notesList.innerHTML = "";
}

const RECENT_NOTES_LIMIT = 10;

function setSearchPanelOpen(isOpen) {
  searchPanel.classList.toggle("search-panel-hidden", !isOpen);
  appShell.classList.toggle("search-open", isOpen);
  toggleSearchBtn.setAttribute("aria-expanded", String(isOpen));
  toggleSearchBtn.innerHTML = isOpen ? CLOSE_ICON_SVG : SEARCH_ICON_SVG;
  toggleSearchBtn.title = isOpen ? "Close search" : "Search";
  toggleSearchBtn.setAttribute("aria-label", isOpen ? "Close search" : "Open search");
  if (!isOpen) {
    // Return to clean capture mode when search closes.
    clearRenderedNotes();
    setStatus("");
    searchInput.value = "";
    return;
  }
  if (isOpen) {
    searchInput.focus();
  }
}

function renderNotes(notes) {
  clearRenderedNotes();
  if (!notes || notes.length === 0) {
    notesList.innerHTML = "<p>No notes found yet.</p>";
    return;
  }

  notesMeta.textContent = `${notes.length} notes found.`;

  for (const note of notes) {
    const noteCard = document.createElement("article");
    noteCard.className = "note";
    noteCard.innerHTML = `
      <p><strong>Summary:</strong> ${note.summary || "No summary yet"}</p>
      <p class="tags"><strong>Tags:</strong> ${formatTags(note.tags)}</p>
      <details>
        <summary>Read Full Note</summary>
        <p>${note.content}</p>
      </details>
      <button class="delete-note-btn" data-note-id="${note.id}">Delete note</button>
      <p class="note-date">${new Date(note.created_at).toLocaleString()}</p>
    `;
    notesList.appendChild(noteCard);
  }

  const deleteButtons = notesList.querySelectorAll(".delete-note-btn");
  for (const button of deleteButtons) {
    button.addEventListener("click", async () => {
      const noteId = button.dataset.noteId;
      await deleteNote(noteId);
    });
  }
}

async function loadRecentNotes() {
  setStatus("Loading recent notes...");
  try {
    const response = await fetchWithTimeout(`${API_BASE_URL}/notes?limit=${RECENT_NOTES_LIMIT}`);
    if (!response.ok) {
      throw new Error("Could not load notes");
    }
    const notes = await response.json();
    renderNotes(notes);
    setStatus(`Loaded ${notes.length} recent notes.`);
  } catch (error) {
    setStatus(getErrorMessage(error, "Could not load recent notes"), true);
  }
}

async function createNote() {
  const content = noteInput.value.trim();
  if (!content) {
    setStatus("Please add some text before saving.", true);
    return;
  }

  setStatus("Saving note...");
  try {
    const response = await fetchWithTimeout(`${API_BASE_URL}/note`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content }),
    });
    if (!response.ok) {
      const errorData = await response.json();
      throw new Error(errorData.detail || "Failed to save note");
    }

    noteInput.value = "";
    autoResizeNoteInput();
    clearRenderedNotes();
    setStatus("Note saved. Notes stay hidden until you search or click Load recent notes.");
  } catch (error) {
    setStatus(getErrorMessage(error, "Failed to save note"), true);
  }
}

async function uploadSelectedFile() {
  const selectedFile = fileInput.files[0] || pendingPastedFile;
  if (!selectedFile) {
    setUploadStatus("Choose a PDF/image file or paste a screenshot first.", true);
    return;
  }

  setStatus("Uploading file...");
  setUploadStatus(`Processing ${selectedFile.name}... this can take up to 1-2 minutes for screenshots.`);
  setUploadInProgress(true, "Running OCR and saving note...");
  try {
    const formData = new FormData();
    formData.append("file", selectedFile, selectedFile.name);

    const response = await fetchWithTimeout(`${API_BASE_URL}/ingest/file`, {
      method: "POST",
      body: formData,
    }, FILE_UPLOAD_TIMEOUT_MS);
    if (!response.ok) {
      const errorData = await response.json();
      throw new Error(errorData.detail || "Failed to upload file");
    }

    fileInput.value = "";
    setPendingPastedFile(null);
    clearRenderedNotes();
    setStatus("File saved as note. Notes stay hidden until you search or click Load recent notes.");
    setUploadStatus("File processed and saved.");
  } catch (error) {
    const message = getErrorMessage(error, "Failed to upload file");
    setStatus(message, true);
    setUploadStatus(message, true);
  } finally {
    setUploadInProgress(false);
  }
}

async function searchNotes() {
  const query = searchInput.value.trim();
  if (!query) {
    clearRenderedNotes();
    setStatus("Type a search query and press Enter, or click Load recent notes.", false);
    return;
  }

  setStatus(`Searching for "${query}"...`);
  try {
    const response = await fetchWithTimeout(`${API_BASE_URL}/search?q=${encodeURIComponent(query)}`);
    if (!response.ok) {
      throw new Error("Search failed");
    }
    const notes = await response.json();
    renderNotes(notes);
    setStatus(`Found ${notes.length} notes.`);
  } catch (error) {
    setStatus(getErrorMessage(error, "Search failed"), true);
  }
}

async function deleteNote(noteId) {
  if (!noteId) {
    return;
  }

  const confirmed = window.confirm("Delete this note?");
  if (!confirmed) {
    return;
  }

  setStatus("Deleting note...");
  try {
    const response = await fetchWithTimeout(`${API_BASE_URL}/note/${noteId}`, {
      method: "DELETE",
    });
    if (!response.ok) {
      const errorData = await response.json();
      throw new Error(errorData.detail || "Failed to delete note");
    }

    setStatus("Note deleted.");
    if (searchInput.value.trim()) {
      await searchNotes();
      return;
    }
    await loadRecentNotes();
  } catch (error) {
    setStatus(getErrorMessage(error, "Failed to delete note"), true);
  }
}

uploadFileBtn.addEventListener("click", uploadSelectedFile);
pickFileBtn.addEventListener("click", () => fileInput.click());
toggleSearchBtn.addEventListener("click", () => {
  const isOpen = searchPanel.classList.contains("search-panel-hidden");
  setSearchPanelOpen(isOpen);
});
loadRecentBtn.addEventListener("click", loadRecentNotes);
fileInput.addEventListener("change", () => {
  const file = fileInput.files[0];
  if (!file) {
    setPendingPastedFile(null);
    return;
  }
  pendingPastedFile = null;
  uploadFileBtn.style.display = "inline-block";
  setUploadStatus(`Attached file ready: ${file.name}`);
});
noteInput.addEventListener("paste", (event) => {
  const items = event.clipboardData?.items || [];
  for (const item of items) {
    if (!item.type.startsWith("image/")) {
      continue;
    }
    const file = item.getAsFile();
    if (!file) {
      continue;
    }
    const extension = file.type.split("/")[1] || "png";
    const pastedFile = new File([file], `pasted-screenshot.${extension}`, { type: file.type });
    setPendingPastedFile(pastedFile);
    fileInput.value = "";
    event.preventDefault();
    return;
  }
});
noteInput.addEventListener("input", autoResizeNoteInput);
noteInput.addEventListener("keydown", (event) => {
  if (event.key !== "Enter" || event.shiftKey) {
    return;
  }
  event.preventDefault();
  createNote();
});
searchInput.addEventListener("keydown", (event) => {
  if (event.key !== "Enter") {
    return;
  }
  event.preventDefault();
  searchNotes();
});

uploadFileBtn.style.display = "none";
setUploadInProgress(false);
setStatus("");
setUploadStatus("");
clearRenderedNotes();
setSearchPanelOpen(false);
autoResizeNoteInput();
