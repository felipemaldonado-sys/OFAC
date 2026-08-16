(function (global) {
  const NAME_THRESHOLD = 50;
  const ID_THRESHOLD = 95;
  const TOKEN_FUZZY = 0.8;

  const STOPWORDS = new Set([
    "de",
    "del",
    "la",
    "el",
    "los",
    "las",
    "y",
    "e",
    "o",
    "en",
    "un",
    "una",
    "the",
    "of",
    "and",
    "for",
    "al",
    "bin",
    "bint",
    "ben",
    "von",
    "van",
    "da",
    "das",
    "do",
    "dos",
    "ltda",
    "ltd",
    "sas",
    "sa",
    "scs",
    "cia",
    "llc",
    "inc",
    "corp",
    "co",
  ]);

  function fold(value) {
    return String(value || "")
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .toLowerCase();
  }

  function tokenize(value) {
    return fold(value)
      .replace(/[^a-z0-9]+/g, " ")
      .trim()
      .split(/\s+/)
      .filter((token) => token.length >= 2 && !STOPWORDS.has(token));
  }

  function levenshtein(a, b) {
    if (a === b) return 0;
    if (!a.length) return b.length;
    if (!b.length) return a.length;

    const prev = new Array(b.length + 1);
    const curr = new Array(b.length + 1);
    for (let j = 0; j <= b.length; j += 1) prev[j] = j;

    for (let i = 1; i <= a.length; i += 1) {
      curr[0] = i;
      for (let j = 1; j <= b.length; j += 1) {
        const cost = a[i - 1] === b[j - 1] ? 0 : 1;
        curr[j] = Math.min(curr[j - 1] + 1, prev[j] + 1, prev[j - 1] + cost);
      }
      for (let j = 0; j <= b.length; j += 1) prev[j] = curr[j];
    }
    return prev[b.length];
  }

  function tokenSimilarity(a, b) {
    if (a === b) return 1;
    const longest = Math.max(a.length, b.length);
    if (!longest) return 0;
    if (Math.abs(a.length - b.length) / longest > 1 - TOKEN_FUZZY) return 0;
    return 1 - levenshtein(a, b) / longest;
  }

  function matchTokens(queryTokens, targetTokens) {
    const used = new Set();
    const pairs = [];

    queryTokens.forEach((queryToken, queryIndex) => {
      let best = 0;
      let bestIndex = -1;
      targetTokens.forEach((targetToken, targetIndex) => {
        if (used.has(targetIndex)) return;
        const similarity = tokenSimilarity(queryToken, targetToken);
        if (similarity > best) {
          best = similarity;
          bestIndex = targetIndex;
        }
      });
      if (bestIndex >= 0 && best >= TOKEN_FUZZY) {
        used.add(bestIndex);
        pairs.push({
          queryIndex,
          targetIndex: bestIndex,
          queryToken,
          targetToken: targetTokens[bestIndex],
          similarity: best,
        });
      }
    });

    return pairs;
  }

  function nameScore(query, targetName, targetTokens) {
    const queryTokens = tokenize(query);
    const resolvedTarget = targetTokens || tokenize(targetName);
    if (!queryTokens.length || !resolvedTarget.length) {
      return { score: 0, pairs: [], queryTokens, targetTokens: resolvedTarget };
    }

    const pairs = matchTokens(queryTokens, resolvedTarget);
    const intersection = pairs.reduce((sum, pair) => sum + pair.similarity, 0);
    const union = queryTokens.length + resolvedTarget.length - intersection;
    const score = union ? (intersection / union) * 100 : 0;

    return {
      score,
      pairs,
      queryTokens,
      targetTokens: resolvedTarget,
    };
  }

  function normalizeId(value) {
    let text = fold(value).replace(/[^a-z0-9]/g, "").toUpperCase();
    if (/^\d+$/.test(text)) {
      text = text.replace(/^0+/, "") || "0";
    }
    return text;
  }

  function idScore(query, identification, idInterno) {
    const queryId = normalizeId(query);
    if (!queryId) return { score: 0, field: null, value: "" };

    const candidates = [
      { field: "identificacion", value: identification || "" },
      { field: "idInterno", value: String(idInterno ?? "") },
    ];

    let best = { score: 0, field: null, value: "" };
    candidates.forEach((candidate) => {
      const target = normalizeId(candidate.value);
      if (!target) return;
      const longest = Math.max(queryId.length, target.length);
      const similarity = (1 - levenshtein(queryId, target) / longest) * 100;
      if (similarity > best.score) {
        best = {
          score: similarity,
          field: candidate.field,
          value: candidate.value,
        };
      }
    });

    return best;
  }

  function search(records, { nombre = "", identificacion = "" } = {}) {
    const nameQuery = nombre.trim();
    const idQuery = identificacion.trim();
    const results = [];

    records.forEach((record) => {
      const nameResult = nameQuery
        ? nameScore(nameQuery, record.nombre, record.tokens)
        : { score: 0, pairs: [] };
      const idResult = idQuery
        ? idScore(idQuery, record.identificacion, record.idInterno)
        : { score: 0, field: null, value: "" };

      const nameHit = Boolean(nameQuery) && nameResult.score >= NAME_THRESHOLD;
      const idHit = Boolean(idQuery) && idResult.score >= ID_THRESHOLD;
      if (!nameHit && !idHit) return;

      const riskScore = Math.max(
        nameHit ? nameResult.score : 0,
        idHit ? idResult.score : 0
      );

      results.push({
        record,
        riskScore,
        nameScore: nameResult.score,
        idScore: idResult.score,
        nameHit,
        idHit,
        pairs: nameResult.pairs,
        idField: idResult.field,
      });
    });

    results.sort((a, b) => {
      if (b.riskScore !== a.riskScore) return b.riskScore - a.riskScore;
      return a.record.nombre.localeCompare(b.record.nombre, "es");
    });

    return results;
  }

  function prepareRecords(rawRecords) {
    return rawRecords.map((record) => ({
      ...record,
      tokens: tokenize(record.nombre),
    }));
  }

  function highlightName(name, pairs) {
    if (!pairs || !pairs.length) return escapeHtml(name);

    const matched = new Set(pairs.map((pair) => pair.targetToken));
    const parts = String(name).match(/[A-Za-zÀ-ÿ0-9]+(?:[-'][A-Za-zÀ-ÿ0-9]+)*|[^A-Za-zÀ-ÿ0-9]+/g) || [name];

    return parts
      .map((part) => {
        if (!/[A-Za-zÀ-ÿ0-9]/.test(part)) return escapeHtml(part);
        const wordTokens = tokenize(part);
        const folded = fold(part).replace(/[^a-z0-9]/g, "");
        const hit =
          wordTokens.some((token) => matched.has(token)) ||
          [...matched].some((token) => tokenSimilarity(folded, token) >= TOKEN_FUZZY);
        return hit ? `<mark>${escapeHtml(part)}</mark>` : escapeHtml(part);
      })
      .join("");
  }

  function escapeHtml(value) {
    return String(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function formatScore(score) {
    return `${score.toFixed(1).replace(/\.0$/, "")}%`;
  }

  function riskLevel(score) {
    if (score >= 85) return "alta";
    if (score >= 70) return "media";
    return "baja";
  }

  global.OfacMatcher = {
    NAME_THRESHOLD,
    ID_THRESHOLD,
    tokenize,
    nameScore,
    idScore,
    search,
    prepareRecords,
    highlightName,
    escapeHtml,
    formatScore,
    riskLevel,
  };
})(window);
