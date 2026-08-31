/* A DOM small enough to run art30/web/index.html's script in Node. Elements hold children,
   attributes, className, hidden and textContent; ids register on setAttribute and on demand.
   Used by tests/test_web_simple_view.py; there is no browser on the build machine. */
function Text(t) { this.nodeType = 3; this.textContent = String(t); this.parentNode = null; }
function Element(tag) {
  this.nodeType = 1; this.tagName = tag.toUpperCase(); this._children = []; this._attrs = {};
  this.className = ""; this.hidden = false; this.style = {}; this.dataset = {}; this.disabled = false;
  this.tabIndex = 0; this.value = ""; this.parentNode = null; this.isConnected = true;
  this.classList = { add: function(){}, remove: function(){}, toggle: function(){} };
}
Element.prototype.appendChild = function (k) { if (k.parentNode) k.parentNode.removeChild(k); k.parentNode = this; this._children.push(k); return k; };
Element.prototype.removeChild = function (k) { var i = this._children.indexOf(k); if (i >= 0) this._children.splice(i, 1); k.parentNode = null; return k; };
Object.defineProperty(Element.prototype, "firstChild", { get: function () { return this._children[0] || null; } });
Object.defineProperty(Element.prototype, "textContent", {
  get: function () { return this._children.map(function (k) { return k.textContent; }).join(""); },
  set: function (v) { this._children = [new Text(v)]; }
});
Element.prototype.setAttribute = function (k, v) { this._attrs[k] = String(v); if (k === "id") registry[v] = this; if (k === "class") this.className = String(v); };
Element.prototype.getAttribute = function (k) { return this._attrs[k] === undefined ? null : this._attrs[k]; };
Element.prototype.removeAttribute = function (k) { delete this._attrs[k]; };
Element.prototype.addEventListener = function () {};
Element.prototype.focus = function () {};
Element.prototype.replaceChildren = function () { this._children = []; for (var i = 0; i < arguments.length; i++) this.appendChild(arguments[i]); };
Element.prototype.scrollIntoView = function () {};
Element.prototype.querySelectorAll = function () { return []; };
Element.prototype.querySelector = function () { return new Element("button"); };
Element.prototype.closest = function () { return null; };
var registry = {};
global.document = {
  createElement: function (t) { return new Element(t); },
  createTextNode: function (t) { return new Text(t); },
  getElementById: function (id) { if (!registry[id]) { registry[id] = new Element("div"); registry[id]._attrs.id = id; } return registry[id]; },
  addEventListener: function () {}, activeElement: null
};
var store = {};
global.window = { localStorage: { getItem: function (k) { return store[k] === undefined ? null : store[k]; }, setItem: function (k, v) { store[k] = String(v); } },
  addEventListener: function () {}, location: { hash: "" } };
global.EventSource = function () { this.addEventListener = function () {}; this.close = function () {}; };
global.fetch = function () { return Promise.resolve({ ok: false, status: 404, json: function () { return Promise.resolve({}); }, text: function () { return Promise.resolve(""); } }); };
global.Element = Element;
process.on("unhandledRejection", function (e) { console.error("unhandled:", e && e.message); });
