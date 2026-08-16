(function () {
  const nameInput = document.getElementById("nombre");
  const idInput = document.getElementById("identificacion");
  const form = document.getElementById("search-form");
  const clearBtn = document.getElementById("clear-btn");
  const exportBtn = document.getElementById("export-btn");
  const resultsBox = document.getElementById("results");
  const totalEl = document.getElementById("total-registros");
  const basesEl = document.getElementById("bases-activas");
  const footEl = document.getElementById("foot-bases");

  let lastResults = [];

  function currentQuery() {
    return {
      nombre: nameInput.value,
      identificacion: idInput.value,
    };
  }

  function renderEmpty(title, text) {
    resultsBox.innerHTML = `
      <div class="empty">
        <h3>${title}</h3>
        <p>${text}</p>
        <div class="examples">
          <button type="button" data-example-name="Cano Correa">Cano Correa</button>
          <button type="button" data-example-name="Ali Kazan">Ali Kazan</button>
          <button type="button" data-example-name="Hamid Ali">Hamid Ali</button>
        </div>
      </div>
    `;
  }

  function renderResults(results, query) {
    lastResults = results;
    exportBtn.hidden = results.length === 0;

    if (!query.nombre.trim() && !query.identificacion.trim()) {
      renderEmpty(
        "Liste y cruce en la misma pantalla",
        "Escriba un nombre, una identificación, o ambos. El motor marca coincidencias de nombre desde 50% y de ID desde 95%."
      );
      return;
    }

    if (!results.length) {
      renderEmpty(
        "Sin coincidencias sobre el umbral",
        "No hubo cruces con score de nombre ≥ 50% ni de identificación ≥ 95%."
      );
      return;
    }

    const rows = results
      .map((item) => {
        const score = OfacMatcher.formatScore(item.riskScore);
        const level = OfacMatcher.riskLevel(item.riskScore);
        const nameHtml = item.nameHit
          ? OfacMatcher.highlightName(item.record.nombre, item.pairs)
          : OfacMatcher.escapeHtml(item.record.nombre);
        const badges = [
          item.nameHit ? `<span class="badge">Nombre ${OfacMatcher.formatScore(item.nameScore)}</span>` : "",
          item.idHit ? `<span class="badge">ID ${OfacMatcher.formatScore(item.idScore)}</span>` : "",
          item.record.base ? `<span class="badge">${OfacMatcher.escapeHtml(item.record.base)}</span>` : "",
        ].join("");

        return `
          <tr>
            <td><span class="score ${level}">${score}</span></td>
            <td>
              <div class="name">${nameHtml}</div>
              <div class="badges">${badges}</div>
            </td>
            <td>
              <div>${OfacMatcher.escapeHtml(item.record.identificacion || "—")}</div>
              <div class="muted">ID interno ${item.record.idInterno}</div>
            </td>
            <td class="lista">${OfacMatcher.escapeHtml(item.record.lista)}</td>
          </tr>
        `;
      })
      .join("");

    resultsBox.innerHTML = `
      <div class="results-head">
        <div>
          <strong>${results.length.toLocaleString("es-CO")} coincidencia${results.length === 1 ? "" : "s"}</strong>
          <div class="muted">Ordenadas por score de riesgo</div>
        </div>
      </div>
      <div style="overflow:auto">
        <table>
          <thead>
            <tr>
              <th>Score</th>
              <th>Nombre</th>
              <th>Identificación</th>
              <th>Lista</th>
            </tr>
          </thead>
          <tbody>${rows}</tbody>
        </table>
      </div>
    `;
  }

  async function loadStats() {
    const response = await fetch("/api/stats");
    if (!response.ok) throw new Error("No se pudo conectar con el backend.");
    const stats = await response.json();
    totalEl.textContent = Number(stats.total || 0).toLocaleString("es-CO");
    if (basesEl) {
      basesEl.textContent = `${stats.baseCount} base${stats.baseCount === 1 ? "" : "s"} activa${stats.baseCount === 1 ? "" : "s"}`;
    }
    if (footEl) {
      const names = (stats.bases || [])
        .filter((base) => Number(base.active) === 1)
        .map((base) => base.name);
      footEl.textContent = names.length
        ? `Bases activas: ${names.join(" · ")}`
        : "No hay bases activas. Cárguelas en Administrar bases.";
    }
  }

  async function runSearch() {
    const query = currentQuery();
    if (!query.nombre.trim() && !query.identificacion.trim()) {
      renderResults([], query);
      return;
    }
    resultsBox.innerHTML = `<div class="empty"><h3>Buscando…</h3><p>Cruzando las bases activas.</p></div>`;
    try {
      const response = await fetch("/api/search", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(query),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || "No se pudo buscar.");
      renderResults(payload.results || [], query);
    } catch (error) {
      renderEmpty("Backend no disponible", error.message);
    }
  }

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    runSearch();
  });

  clearBtn.addEventListener("click", () => {
    nameInput.value = "";
    idInput.value = "";
    lastResults = [];
    exportBtn.hidden = true;
    renderResults([], currentQuery());
    nameInput.focus();
  });

  resultsBox.addEventListener("click", (event) => {
    const button = event.target.closest("[data-example-name]");
    if (!button) return;
    nameInput.value = button.getAttribute("data-example-name");
    idInput.value = "";
    runSearch();
  });

  exportBtn.addEventListener("click", () => {
    if (!lastResults.length) return;
    const header = ["Score riesgo", "Nombre", "Identificacion", "ID interno", "Lista", "Base", "Score nombre", "Score ID"];
    const lines = [header.join(",")].concat(
      lastResults.map((item) =>
        [
          item.riskScore.toFixed(1),
          `"${item.record.nombre.replace(/"/g, '""')}"`,
          `"${(item.record.identificacion || "").replace(/"/g, '""')}"`,
          item.record.idInterno,
          item.record.lista,
          `"${(item.record.base || "").replace(/"/g, '""')}"`,
          item.nameScore.toFixed(1),
          item.idScore.toFixed(1),
        ].join(",")
      )
    );
    const blob = new Blob(["\uFEFF" + lines.join("\n")], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "coincidencias-ofac.csv";
    link.click();
    URL.revokeObjectURL(url);
  });

  renderResults([], currentQuery());
  loadStats().catch((error) => {
    renderEmpty("Backend no disponible", error.message);
  });
})();
