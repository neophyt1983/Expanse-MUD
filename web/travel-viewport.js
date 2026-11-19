/* Terrain only. Actors, doors, light and discovery always come from the current map. */
(() => {
  let sequence = 0;
  const clamp = n => Math.max(1, Math.min(64, n));
  const halfExtent = (pixels, unit) => clamp(Math.ceil((pixels / unit - 1) / 2) + 2);
  const sameSize = (a, b) => a && b && a[0] === b[0] && a[1] === b[1];
  const covers = (a, b) => a && a[0] >= b[0] && a[1] >= b[1];
  const at = (x, y) => x + ',' + y;
  class TravelViewport {
    constructor() { this.reset(); }
    reset() {
      this.packet = null;
      this.ground = new Map();
      this.pending = null;
      this.extent = null;
      this.coverage = null;
    }
    update(packet) {
      const v = packet.visual, prev = this.packet, old = prev?.visual;
      if (prev === packet) return;
      const samePlane = old && old.context?.id === v.context?.id && old.floor === v.floor &&
        prev.character?.id === packet.character?.id && old.travel_world === v.travel_world &&
        old.geometry_revision === v.geometry_revision;
      if (!samePlane) this.reset();
      else if (old.center !== v.center) {
        const here = v.tiles.find(t => t.current), before = old.tiles.find(t => t.current);
        const delta = here && before && {dx:here.x-before.x, dy:here.y-before.y};
        const anchor = delta && Math.max(Math.abs(delta.dx), Math.abs(delta.dy)) <= 1
          ? delta : [...this.ground.values()].find(t => t.id === v.center);
        const doorway = old.exits?.some(e => e.target === v.center && e.kind === 'portal');
        const carried = new Map();
        if (!doorway && anchor && Math.max(Math.abs(anchor.dx), Math.abs(anchor.dy)) <= 1) {
          for (const t of this.ground.values()) {
            const dx = t.dx - anchor.dx, dy = t.dy - anchor.dy;
            if (Math.abs(dx) <= (this.extent?.[0] ?? 64) && Math.abs(dy) <= (this.extent?.[1] ?? 64))
              carried.set(at(dx, dy), {...t, dx, dy});
          }
        }
        this.ground = carried;
        this.pending = null;
        this.coverage = null;
      }
      this.packet = packet;
      if (Array.isArray(v.opening_tiles)) {
        this.replace(v.opening_tiles, v.opening_extent);
        if (v.opening_extent && (!this.coverage || covers(v.opening_extent, this.coverage) ||
            (this.extent && covers(v.opening_extent, this.extent)))) this.coverage = v.opening_extent;
      }
    }
    replace(tiles, extent) {
      // Older hosts send only the streets reachable from this viewpoint.
      // Absence from those outdoor observations cannot erase a surveyed tile.
      const v = this.packet.visual;
      const complete = v.context?.kind !== 'outdoors' || v.surface_survey === true;
      if (complete && extent) {
        for (const [key, t] of this.ground) {
          if (Math.abs(t.dx) <= extent[0] && Math.abs(t.dy) <= extent[1])
            this.ground.delete(key);
        }
      }
      for (const t of tiles) this.ground.set(at(t.dx, t.dy), t);
    }
    measure(width, height, unit, send) {
      if (!this.packet || !width || !height || !unit) return;
      const extent = [halfExtent(width, unit), halfExtent(height, unit)];
      this.extent = extent;
      const v = this.packet.visual;
      const resizeSubscription = v.follow_view === true && !sameSize(v.follow_extent, extent);
      if (sameSize(this.pending?.extent, extent)) return;
      if (!resizeSubscription && covers(this.coverage, extent)) {
        this.pending = null;
        return;
      }
      const id = ++sequence;
      this.pending = {id, extent, geometry_revision:v.geometry_revision};
      if (send(v.center, extent, id) === false) this.pending = null;
    }
    receive(message) {
      if (!this.pending || message.request_id !== this.pending.id || message.center !== this.packet?.visual.center) return false;
      if (message.geometry_revision !== undefined && message.geometry_revision !== this.pending?.geometry_revision) return false;
      if (!Array.isArray(message.tiles) || !message.tiles.some(t => t.id === message.center && t.dx === 0 && t.dy === 0))
        return false;
      this.replace(message.tiles, this.pending.extent);
      this.coverage = this.pending.extent;
      // Retain the request dimensions until the server echoes the subscription.
      // This also prevents redundant requests on an older host between steps.
      return true;
    }
    tiles(center) {
      const cells = new Map(), nearest = new Map();
      for (const ground of this.ground.values()) {
        if (this.extent && (Math.abs(ground.dx)>this.extent[0] || Math.abs(ground.dy)>this.extent[1])) continue;
        const x=center.x+ground.dx, y=center.y+ground.dy;
        const tile={...ground,x,y,z:center.z,landscape:true,visibility:'terrain',
          name:ground.name || (ground.terrain==='building' ? 'Building exterior' : String(ground.terrain || 'Terrain').replaceAll('_',' '))};
        cells.set(at(x,y),tile);
        const previous=nearest.get(tile.id);
        if (!previous || Math.abs(tile.dx)+Math.abs(tile.dy)<Math.abs(previous.dx)+Math.abs(previous.dy))
          nearest.set(tile.id,tile);
      }
      const observations = new Map();
      for (const live of this.packet.visual.tiles) {
        const position=live.current ? center : nearest.get(live.id) || live;
        const key=at(position.x,position.y);
        if (!observations.has(key)) observations.set(key,[]);
        observations.get(key).push(live);
      }
      for (const [key, nearby] of observations) {
        const ground=cells.get(key);
        const live=nearby.find(t=>t.current) || nearby.find(t=>t.id===ground?.id) || nearby[0];
        const tile=ground ? {...live,...ground} : {...live};
        // Keep all occupants addressable at a shared public doorstep. The survey
        // owns the floor and roof; the current observation owns names and actors.
        if (!ground || live.current || live.id===ground.id || !ground.scenery) {
          Object.assign(tile,{id:live.id,name:live.name,landscape:false,visibility:live.visibility});
          if (ground && live.id!==ground.id) tile.surface_id=ground.surface_id || ground.id;
        }
        if (ground) {
          for (const key of ['roof_joins','route_surface','ground_use','ground_landform','pixel_art','facility_landmark']) {
            if (!(key in ground)) delete tile[key];
          }
          if (ground.terrain!=='building') tile.exterior=false;
        }
        tile.room_ids=[...new Set([...nearby.map(t=>t.id), ...(ground && !ground.scenery ? [ground.id] : [])])];
        cells.set(key,tile);
      }
      const tiles=[...cells.values()];
      return tiles;
    }
  }
  window.ExpanseTravelViewport = TravelViewport;
})();
