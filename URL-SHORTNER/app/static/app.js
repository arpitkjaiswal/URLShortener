// app/static/app.js
// Single-file JavaScript for the URL Shortener Dashboard
// Handles form submission, recent URLs rendering, stats modal, and toast notifications.

document.addEventListener('DOMContentLoaded', () => {
  // Elements
  const form = document.getElementById('shorten-form');
  const urlInput = document.getElementById('url-input');
  const ttlInput = document.getElementById('ttl-input');
  const ttlUnit = document.getElementById('ttl-unit');
  const submitBtn = form.querySelector('button[type=\"submit\"]');
  const recentContainer = document.getElementById('recent-urls');
  const toastContainer = document.getElementById('toast-container');
  const statsModal = document.getElementById('stats-modal');
  const statsBody = document.getElementById('stats-body');
  const modalClose = document.getElementById('modal-close');

  // Enable submit when URL has value
  urlInput.addEventListener('input', () => {
    submitBtn.disabled = urlInput.value.trim().length === 0;
  });

  // Helper: show toast
  function showToast(message, type = 'info') {
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = message;
    toastContainer.appendChild(toast);
    setTimeout(() => toast.remove(), 3000);
  }

  // Helper: format date
  function formatDate(iso) {
    if (!iso) return '—';
    const d = new Date(iso);
    return d.toLocaleString();
  }

  // Render a single URL card
  function renderUrlCard(item) {
    const card = document.createElement('div');
    card.className = 'card recent-card';
    card.dataset.shortCode = item.short_code;
    card.innerHTML = `
      <div class="card-header">
        <span class="short-code">${item.short_code}</span>
        <button class="btn copy-btn" title="Copy short URL">📋</button>
        <button class="btn open-btn" title="Open link">🔗</button>
        <button class="btn stats-btn" title="View stats">📊</button>
        <button class="btn delete-btn" title="Delete URL">🗑️</button>
      </div>
      <div class="card-body">
        <p class="original-url" title="${item.original_url}">${item.original_url}</p>
        <p class="meta">Created: ${formatDate(item.created_at)} | Clicks: ${item.clicks}</p>
      </div>
      <div class="stats-content hidden"></div>
    `;
    // Copy button
    card.querySelector('.copy-btn').addEventListener('click', async () => {
      try {
        await navigator.clipboard.writeText(item.short_url);
        showToast('Short URL copied!', 'success');
      } catch (e) {
        showToast('Copy failed', 'error');
      }
    });
    // Open button
    card.querySelector('.open-btn').addEventListener('click', () => {
      window.open(item.short_url, '_blank');
    });
    // Stats button
    card.querySelector('.stats-btn').addEventListener('click', async () => {
      const statsDiv = card.querySelector('.stats-content');
      if (!statsDiv.classList.contains('hidden')) {
        // Hide stats if already shown
        statsDiv.classList.add('hidden');
        return;
      }
      try {
        const resp = await fetch(`http://127.0.0.1:8000/api/v1/stats/${item.short_code}`);
        if (!resp.ok) throw new Error('Failed');
        const data = await resp.json();
        statsDiv.innerHTML = `
          <p><strong>Original:</strong> ${data.original_url}</p>
          <p><strong>Short:</strong> ${data.short_code}</p>
          <p><strong>Clicks:</strong> ${data.clicks}</p>
          <p><strong>Created:</strong> ${formatDate(data.created_at)}</p>
          <p><strong>Expires:</strong> ${formatDate(data.expires_at)}</p>
          <p><strong>Last accessed:</strong> ${formatDate(data.last_accessed)}</p>
        `;
        statsDiv.classList.remove('hidden');
      } catch (e) {
        showToast('Unable to load stats', 'error');
      }
    });
    // Delete button handler
    card.querySelector('.delete-btn').addEventListener('click', async () => {
      try {
        const resp = await fetch(`http://127.0.0.1:8000/api/v1/urls/${item.short_code}`, { method: 'DELETE' });
        if (!resp.ok) throw new Error('Failed');
        card.remove();
        showToast('URL deleted', 'success');
      } catch (e) {
        showToast('Delete failed', 'error');
      }
    });
    recentContainer.prepend(card);
  }

  // Load recent URLs on page load
  async function loadRecent() {
    try {
      const resp = await fetch('http://127.0.0.1:8000/api/v1/urls');
      if (!resp.ok) throw new Error('Network response was not ok');
      const data = await resp.json();
      recentContainer.innerHTML = '';
      data.forEach(renderUrlCard);
    } catch (e) {
      showToast('Failed to load recent URLs', 'error');
    }
  }

  // Form submission handler
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const url = urlInput.value.trim();
    let ttlSeconds = null;
    if (ttlInput.value) {
      const unit = ttlUnit.value;
      const val = parseInt(ttlInput.value, 10);
      const multipliers = { seconds: 1, minutes: 60, hours: 3600, days: 86400 };
      ttlSeconds = val * (multipliers[unit] || 1);
    }
    const payload = { url };
    if (ttlSeconds !== null) payload.ttl_seconds = ttlSeconds;
    try {
      const resp = await fetch('http://127.0.0.1:8000/api/v1/shorten', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.detail || 'Error');
      // Append new URL to recent list
      const newItem = {
        short_code: data.short_code,
        original_url: url,
        short_url: data.short_url,
        created_at: new Date().toISOString(),
        expires_at: data.expires_at,
        clicks: 0,
      };
      renderUrlCard(newItem);
      showToast('URL shortened!', 'success');
      form.reset();
      submitBtn.disabled = true;
    } catch (err) {
      showToast(err.message ?? 'Failed to shorten URL', 'error');
    }
  });

  // Modal close handler
  modalClose.addEventListener('click', () => {
    statsModal.classList.add('hidden');
  });

  // Initial load
  loadRecent();
});
