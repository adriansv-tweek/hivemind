const API_BASE_URL = "http://127.0.0.1:8000";

const noteInput = document.getElementById("noteInput");
const saveNoteBtn = document.getElementById("saveNoteBtn");
const searchInput = document.getElementById("searchInput");
const searchBtn = document.getElementById("searchBtn");
const loadAllBtn = document.getElementById("loadAllBtn");
const notesList = document.getElementById("notesList");
const statusText = document.getElementById("statusText");
const REQUEST_TIMEOUT_MS = 20000;

function setStatus(message, isError = false) {
  statusText.textContent = message;
  statusText.style.color = isError ? "#b42318" : "#333";
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

function renderNotes(notes) {
  notesList.innerHTML = "";
  if (!notes || notes.length === 0) {
    notesList.innerHTML = "<p>No notes found yet.</p>";
    return;
  }

  for (const note of notes) {
    const noteCard = document.createElement("article");
    noteCard.className = "note";
    noteCard.innerHTML = `
      <p><strong>Summary:</strong> ${note.summary || "No summary yet"}</p>
      <p class="tags"><strong>Tags:</strong> ${formatTags(note.tags)}</p>
      <details>
        <summary>Read full note</summary>
        <p>${note.content}</p>
      </details>
      <p><small>${new Date(note.created_at).toLocaleString()}</small></p>
    `;
    notesList.appendChild(noteCard);
  }
}

async function loadAllNotes() {
  setStatus("Loading notes...");
  try {
    const response = await fetchWithTimeout(`${API_BASE_URL}/notes`);
    if (!response.ok) {
      throw new Error("Could not load notes");
    }
    const notes = await response.json();
    renderNotes(notes);
    setStatus(`Loaded ${notes.length} notes.`);
  } catch (error) {
    setStatus(getErrorMessage(error, "Could not load notes"), true);
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
    setStatus("Note saved.");
    await loadAllNotes();
  } catch (error) {
    setStatus(getErrorMessage(error, "Failed to save note"), true);
  }
}

async function searchNotes() {
  const query = searchInput.value.trim();
  if (!query) {
    await loadAllNotes();
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

saveNoteBtn.addEventListener("click", createNote);
searchBtn.addEventListener("click", searchNotes);
loadAllBtn.addEventListener("click", loadAllNotes);

loadAllNotes();
