/* Le Croustillant — fonctions premium : barre de progression + recherche interne.
   Vanilla JS, aucun service externe, aucun cookie. */
(function () {
  "use strict";

  /* ---------- Barre de progression de lecture ---------- */
  var bar = document.getElementById("progress");
  if (bar) {
    var ticking = false;
    var update = function () {
      var h = document.documentElement;
      var max = h.scrollHeight - h.clientHeight;
      bar.style.width = (max > 0 ? (h.scrollTop / max) * 100 : 0) + "%";
      ticking = false;
    };
    window.addEventListener("scroll", function () {
      if (!ticking) { ticking = true; requestAnimationFrame(update); }
    }, { passive: true });
    update();
  }

  /* ---------- Recherche interne ---------- */
  var btn = document.getElementById("search-btn");
  if (!btn) return;

  var overlay = null;
  var index = null;

  function norm(s) {
    return (s || "").toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "");
  }

  function buildOverlay() {
    overlay = document.createElement("div");
    overlay.className = "search-overlay";
    overlay.innerHTML =
      '<div class="search-panel" role="dialog" aria-label="Recherche">' +
      '<div class="search-bar-row">' +
      '<input type="search" class="search-input" placeholder="Rechercher une recette, un guide, un comparatif..." aria-label="Rechercher">' +
      '<button type="button" class="search-close" aria-label="Fermer">✕</button>' +
      "</div>" +
      '<ul class="search-results" role="listbox"></ul>' +
      '<p class="search-hint">Astuce : ouvrez la recherche n\u2019importe o\u00f9 avec Ctrl+K</p>' +
      "</div>";
    document.body.appendChild(overlay);

    overlay.addEventListener("click", function (e) {
      if (e.target === overlay) close();
    });
    overlay.querySelector(".search-close").addEventListener("click", close);
    overlay.querySelector(".search-input").addEventListener("input", function () {
      render(this.value);
    });
  }

  function open() {
    if (!overlay) buildOverlay();
    overlay.classList.add("is-open");
    document.body.style.overflow = "hidden";
    var input = overlay.querySelector(".search-input");
    input.value = "";
    render("");
    setTimeout(function () { input.focus(); }, 50);
    if (index === null) {
      fetch("/search-index.json")
        .then(function (r) { return r.json(); })
        .then(function (data) { index = data; render(overlay.querySelector(".search-input").value); })
        .catch(function () { index = []; });
    }
  }

  function close() {
    if (overlay) overlay.classList.remove("is-open");
    document.body.style.overflow = "";
  }

  function render(query) {
    var ul = overlay.querySelector(".search-results");
    var q = norm(query.trim());
    if (index === null) {
      ul.innerHTML = '<li class="search-empty">Chargement…</li>';
      return;
    }
    var pool = index;
    if (q) {
      var words = q.split(/\s+/);
      pool = index.filter(function (a) {
        var hay = norm(a.t + " " + a.d + " " + a.k);
        return words.every(function (w) { return hay.indexOf(w) !== -1; });
      });
    }
    var results = pool.slice(0, 8);
    if (!results.length) {
      ul.innerHTML = '<li class="search-empty">Aucun résultat pour « ' +
        query.replace(/</g, "&lt;") + " »</li>";
      return;
    }
    ul.innerHTML = results.map(function (a) {
      return '<li><a href="' + a.u + '">' +
        '<span class="search-cat">' + a.c + "</span>" +
        '<span class="search-title">' + a.t.replace(/</g, "&lt;") + "</span>" +
        '<span class="search-desc">' + a.d.replace(/</g, "&lt;") + "</span>" +
        "</a></li>";
    }).join("");
  }

  btn.addEventListener("click", open);
  document.addEventListener("keydown", function (e) {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
      e.preventDefault();
      open();
    } else if (e.key === "Escape") {
      close();
    }
  });
})();
