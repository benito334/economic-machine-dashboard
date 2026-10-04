// Shared crosshair for chart cards flagged sync_hover=True (class "sync-hover-card").
// Hovering one card shows the same date on every other card on the page — each card
// snaps to its own nearest observation at or before that date; cards with no data yet
// at that date show nothing. Replaces the old stacked-subplot shared hover now that
// each metric is its own figure.
(function () {
  var syncing = false;

  function graphs() {
    return Array.prototype.slice.call(
      document.querySelectorAll('.sync-hover-card .js-plotly-plot'));
  }

  function toMs(v) { return typeof v === 'number' ? v : Date.parse(v); }

  // Index of the last x <= t in a sorted array, or -1.
  function lastAtOrBefore(xs, t) {
    var lo = 0, hi = xs.length - 1, ans = -1;
    while (lo <= hi) {
      var mid = (lo + hi) >> 1;
      if (toMs(xs[mid]) <= t) { ans = mid; lo = mid + 1; } else { hi = mid - 1; }
    }
    return ans;
  }

  function showAt(gd, t) {
    var pts = [];
    (gd.data || []).forEach(function (tr, ci) {
      if (!tr.x || !tr.x.length || tr.visible === false) return;
      var i = lastAtOrBefore(tr.x, t);
      if (i >= 0) pts.push({ curveNumber: ci, pointNumber: i });
    });
    if (pts.length) Plotly.Fx.hover(gd, pts); else Plotly.Fx.unhover(gd);
  }

  function bind(gd) {
    if (gd._syncHoverBound || typeof gd.on !== 'function') return;
    gd._syncHoverBound = true;
    gd.on('plotly_hover', function (ev) {
      if (syncing || !ev || !ev.points || !ev.points.length) return;
      var t = toMs(ev.points[0].x);
      if (isNaN(t)) return;
      syncing = true;
      try {
        graphs().forEach(function (other) { if (other !== gd) showAt(other, t); });
      } finally { syncing = false; }
    });
    gd.on('plotly_unhover', function () {
      if (syncing) return;
      syncing = true;
      try {
        graphs().forEach(function (other) { if (other !== gd) Plotly.Fx.unhover(other); });
      } finally { syncing = false; }
    });
  }

  function scan() { graphs().forEach(bind); }

  var timer = null;
  new MutationObserver(function () {
    // Throttle, not debounce: a page that mutates continuously must still get scanned.
    if (timer) return;
    timer = setTimeout(function () { timer = null; scan(); }, 200);
  }).observe(document.documentElement, { childList: true, subtree: true });
  scan();
})();
