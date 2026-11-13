/* Fetch public media from the world selected on the connected host or offline worker. */
(() => {
  const cache = new Map(), requests = new Map();
  let sequence = 0, current = '';
  function reset(world) {
    if (world === current) return;
    current = world;
    for (const job of requests.values()) job.finish(null);
    for (const value of cache.values()) value.then(asset => { if (asset?.url) URL.revokeObjectURL(asset.url); });
    cache.clear();
    window.dispatchEvent(new Event('expanse:world-assets'));
  }
  function get(path) {
    if (!current || !path) return Promise.resolve(null);
    if (cache.has(path)) return cache.get(path);
    const id = ++sequence;
    const task = new Promise(resolve => {
      const chunks = [];
      let offset = 0, timer;
      function finish(value) {
        clearTimeout(timer);
        requests.delete(id);
        resolve(value);
      }
      function request() {
        clearTimeout(timer);
        timer = setTimeout(() => finish(null), 15000);
        if (!window.expanseAssetSend?.({command:'world asset',name:path,offset,request_id:id})) finish(null);
      }
      requests.set(id,{finish,receive(row) {
        if (row.missing || row.name !== path || row.offset !== offset || row.size > 32*1024*1024) return finish(null);
        const bytes = Uint8Array.from(atob(row.data), c => c.charCodeAt(0));
        chunks.push(bytes);
        offset += bytes.length;
        if (offset === row.size) {
          const blob = new Blob(chunks,{type:row.mime});
          finish({url:URL.createObjectURL(blob),blob});
        } else if (bytes.length && offset < row.size) request();
        else finish(null);
      }});
      request();
    });
    cache.set(path,task);
    return task;
  }
  function receive(row) {
    if (row.type === 'map') reset(row.media_world || '');
    if (row.type !== 'world_asset') return false;
    requests.get(row.request_id)?.receive(row);
    return true;
  }
  window.ExpanseAssets={get,receive,reset};
})();
