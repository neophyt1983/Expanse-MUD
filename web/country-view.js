/* Size the terrain request to the player's map panel. */
(() => {
  const viewport = new window.ExpanseTravelViewport();
  let targets = new Set();
  function reset() { viewport.reset(); targets.clear(); }
  function paint() {
    const packet = viewport.packet;
    if (!packet) return;
    const visual = packet.visual, center = visual.tiles.find(t => t.current);
    const tiles = viewport.tiles(center);
    targets = new Set(tiles.map(t => t.id));
    window.ExpanseMap.render({...packet, visual:{...visual, tiles}});
  }
  function measure() {
    const canvas = document.querySelector('#player-visual-map canvas.atlas-canvas');
    if (!canvas || !viewport.packet?.visual.travel_window) return;
    const view = canvas.parentElement, unit = Number(canvas.dataset.tilePixels);
    viewport.measure(view.clientWidth, view.clientHeight, unit, (center, extent, id) => {
      if (ws?.readyState !== 1) return false;
      ws.send(JSON.stringify({command:'travel map window',center,extent,request_id:id,follow_view:true}));
    });
  }
  function receive(msg) {
    if (msg.type !== 'travel_window') return false;
    if (viewport.receive(msg)) { window.ExpanseMap.loadPixelAssets(msg.pixel_assets); paint(); }
    return true;
  }
  function render(packet) {
    if (!packet?.visual?.travel_window || !packet.visual.tiles?.some(t => t.current)) {
      reset();
      window.ExpanseMap.render(packet);
      return;
    }
    viewport.update(packet);
    paint();
    requestAnimationFrame(measure);
  }
  const pane = document.getElementById('player-visual-map');
  if (pane) new ResizeObserver(measure).observe(pane.querySelector('.atlas-viewport')||pane);
  window.addEventListener('expanse:display',()=>requestAnimationFrame(measure));
  document.addEventListener('change', e => {
    if (e.target.matches('.atlas-zoom,select')) requestAnimationFrame(() => requestAnimationFrame(measure));
  });
  window.ExpanseCountryView = {receive, render, reset, walkOptions:id => targets.has(id) ?
    {center:viewport.packet.visual.center, extent:viewport.extent || viewport.packet.visual.opening_extent} : {}};
  if (window.latestMap) render(window.latestMap);
})();
