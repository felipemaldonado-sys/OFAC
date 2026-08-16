(function () {
  const form = document.getElementById("upload-form");
  const fileInput = document.getElementById("archivo");
  const nameInput = document.getElementById("nombre");
  const statusEl = document.getElementById("upload-status");
  const button = document.getElementById("upload-btn");
  const totalEl = document.getElementById("total-registros");
  const box = document.getElementById("bases");
  const hostingForm = document.getElementById("hosting-form");
  const repoInput = document.getElementById("repo");
  const tokenInput = document.getElementById("token");
  const hostingBtn = document.getElementById("hosting-btn");
  const publishBtn = document.getElementById("publish-btn");
  const hostingStatus = document.getElementById("hosting-status");
  const hostingMessage = document.getElementById("hosting-message");

  function showStatus(text, kind) {
    statusEl.hidden = false;
    statusEl.textContent = text;
    statusEl.className = `status ${kind || ""}`;
  }

  function renderHosting(hosting) {
    if (!hosting) return;
    if (hosting.repo) repoInput.value = hosting.repo;
    hostingMessage.textContent = hosting.message;
    hostingStatus.hidden = false;
    hostingStatus.className = `status ${hosting.configured && hosting.ok ? "ok" : hosting.error ? "error" : ""}`;
    hostingStatus.textContent = hosting.configured
      ? hosting.ok
        ? `Conectado a ${hosting.repo}`
        : hosting.error || "No se pudo verificar GitHub"
      : "GitHub no conectado. La base queda en este Mac hasta que lo conecte.";
  }

  function render(stats) {
    totalEl.textContent = Number(stats.total || 0).toLocaleString("es-CO");
    renderHosting(stats.hosting);
    const bases = stats.bases || [];
    if (!bases.length) {
      box.innerHTML = `<div class="empty"><h3>Aún no hay bases</h3><p>Suba un Excel con la estructura de la plantilla.</p></div>`;
      return;
    }

    const rows = bases
      .map((base) => {
        const active = Number(base.active) === 1;
        return `
          <tr>
            <td>
              <div class="name">${escapeHtml(base.name)}</div>
              <div class="muted">${escapeHtml(base.filename)}</div>
            </td>
            <td>${Number(base.row_count).toLocaleString("es-CO")}</td>
            <td>${escapeHtml(base.created_at)}</td>
            <td>
              <span class="badge ${active ? "on" : "off"}">${active ? "Activa" : "Apagada"}</span>
            </td>
            <td>
              <div class="row-actions">
                <button type="button" class="ghost" data-toggle="${base.id}" data-active="${active ? 0 : 1}">
                  ${active ? "Apagar" : "Activar"}
                </button>
                <button type="button" class="danger" data-delete="${base.id}">Borrar</button>
              </div>
            </td>
          </tr>
        `;
      })
      .join("");

    box.innerHTML = `
      <div class="results-head">
        <div>
          <strong>${bases.length} base${bases.length === 1 ? "" : "s"}</strong>
          <div class="muted">${stats.baseCount} activa${stats.baseCount === 1 ? "" : "s"} en el buscador</div>
        </div>
      </div>
      <div style="overflow:auto">
        <table>
          <thead>
            <tr>
              <th>Base</th>
              <th>Registros</th>
              <th>Cargada</th>
              <th>Estado</th>
              <th></th>
            </tr>
          </thead>
          <tbody>${rows}</tbody>
        </table>
      </div>
    `;
  }

  function escapeHtml(value) {
    return String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  async function loadStats() {
    const response = await fetch("/api/stats");
    if (!response.ok) throw new Error("No se pudo leer el backend.");
    const stats = await response.json();
    render(stats);
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!fileInput.files[0]) {
      showStatus("Seleccione un archivo Excel.", "error");
      return;
    }
    const data = new FormData();
    data.append("archivo", fileInput.files[0]);
    data.append("nombre", nameInput.value.trim());
    button.disabled = true;
    showStatus("Cargando y indexando la base…", "");
    try {
      const response = await fetch("/api/bases", { method: "POST", body: data });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || "No se pudo subir el archivo.");
      const hosted = payload.stats && payload.stats.hosting && payload.stats.hosting.ok;
      showStatus(
        hosted
          ? `Base cargada y publicada en GitHub: ${payload.base.row_count.toLocaleString("es-CO")} registros.`
          : `Base cargada en este computador: ${payload.base.row_count.toLocaleString("es-CO")} registros. Conecte GitHub para alojarla en internet.`,
        hosted ? "ok" : ""
      );
      form.reset();
      render(payload.stats);
    } catch (error) {
      showStatus(error.message, "error");
    } finally {
      button.disabled = false;
    }
  });

  box.addEventListener("click", async (event) => {
    const toggle = event.target.closest("[data-toggle]");
    const remove = event.target.closest("[data-delete]");
    try {
      if (toggle) {
        const response = await fetch(`/api/bases/${toggle.getAttribute("data-toggle")}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ active: toggle.getAttribute("data-active") === "1" }),
        });
        const payload = await response.json();
        if (!response.ok) throw new Error(payload.detail || "No se pudo actualizar.");
        render(payload.stats);
      }
      if (remove) {
        if (!confirm("¿Borrar esta base y todos sus registros?")) return;
        const response = await fetch(`/api/bases/${remove.getAttribute("data-delete")}`, { method: "DELETE" });
        const payload = await response.json();
        if (!response.ok) throw new Error(payload.detail || "No se pudo borrar.");
        render(payload.stats);
      }
    } catch (error) {
      showStatus(error.message, "error");
    }
  });

  hostingForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    hostingBtn.disabled = true;
    hostingStatus.hidden = false;
    hostingStatus.className = "status";
    hostingStatus.textContent = "Conectando con GitHub…";
    try {
      const response = await fetch("/api/hosting", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ repo: repoInput.value.trim(), token: tokenInput.value.trim() }),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || "No se pudo conectar.");
      tokenInput.value = "";
      renderHosting(payload);
    } catch (error) {
      renderHosting({ configured: false, ok: false, error: error.message, message: error.message });
    } finally {
      hostingBtn.disabled = false;
    }
  });

  publishBtn.addEventListener("click", async () => {
    publishBtn.disabled = true;
    hostingStatus.hidden = false;
    hostingStatus.className = "status";
    hostingStatus.textContent = "Publicando bases en GitHub…";
    try {
      const response = await fetch("/api/hosting/publish", { method: "POST" });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || "No se pudo publicar.");
      renderHosting(payload);
      hostingStatus.textContent = `Publicadas en ${payload.repo}`;
      hostingStatus.className = "status ok";
    } catch (error) {
      hostingStatus.className = "status error";
      hostingStatus.textContent = error.message;
    } finally {
      publishBtn.disabled = false;
    }
  });

  loadStats().catch((error) => {
    box.innerHTML = `<div class="empty"><h3>Backend no disponible</h3><p>${escapeHtml(error.message)}</p></div>`;
  });
})();
