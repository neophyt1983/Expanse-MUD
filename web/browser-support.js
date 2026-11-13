// Older embedded Chromium clients use the same player views.
if (!Element.prototype.replaceChildren) {
  for (const prototype of [Element.prototype, Document.prototype, DocumentFragment.prototype]) {
    Object.defineProperty(prototype, 'replaceChildren', {configurable:true, writable:true, value:function(...nodes) {
      while (this.firstChild) this.removeChild(this.firstChild);
      this.append(...nodes);
    }});
  }
}
if (!Object.hasOwn) Object.hasOwn = (obj, prop) => Object.prototype.hasOwnProperty.call(obj, prop);
if (!String.prototype.replaceAll) Object.defineProperty(String.prototype,'replaceAll',{
  configurable:true, writable:true, value:function(pattern,replacement) {
    if (pattern instanceof RegExp) {
      if (!pattern.global) throw new TypeError('replaceAll requires a global regular expression');
      return this.replace(pattern,replacement);
    }
    const escaped = String(pattern).replace(/[.*+?^${}()|[\]\\]/g,'\\$&');
    return this.replace(new RegExp(escaped,'g'),replacement);
  }
});
