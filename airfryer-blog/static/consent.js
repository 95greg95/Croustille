/* Consentement cookies (RGPD) + chargement de Google AdSense Auto Ads.
   AdSense n'est chargé qu'après acceptation explicite. Le choix est mémorisé. */
(function () {
  var script = document.currentScript;
  var client = script && script.getAttribute("data-adsense-client");
  if (!client || client.indexOf("XXXX") !== -1) return;

  var KEY = "consent-ads";

  function loadAds() {
    var s = document.createElement("script");
    s.async = true;
    s.src = "https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=" + encodeURIComponent(client);
    s.crossOrigin = "anonymous";
    document.head.appendChild(s);
  }

  function showBanner() {
    var b = document.createElement("div");
    b.className = "consent-banner";
    b.setAttribute("role", "dialog");
    b.setAttribute("aria-label", "Consentement aux cookies");
    b.innerHTML =
      '<p>Ce site est financé par la publicité. Acceptez-vous les cookies publicitaires de Google ? ' +
      '<a href="/confidentialite/">En savoir plus</a></p>' +
      '<div class="consent-actions">' +
      '<button type="button" class="consent-accept">Accepter</button>' +
      '<button type="button" class="consent-refuse">Refuser</button>' +
      "</div>";
    document.body.appendChild(b);
    b.querySelector(".consent-accept").addEventListener("click", function () {
      localStorage.setItem(KEY, "yes");
      b.remove();
      loadAds();
    });
    b.querySelector(".consent-refuse").addEventListener("click", function () {
      localStorage.setItem(KEY, "no");
      b.remove();
    });
  }

  function init() {
    var choice = localStorage.getItem(KEY);
    if (choice === "yes") loadAds();
    else if (choice !== "no") showBanner();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
